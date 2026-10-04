#include <ctype.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "esp_check.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "carrier_profile.h"

#define IR_TX_GPIO GPIO_NUM_5
#define RMT_RESOLUTION_HZ 1000000U
#define IR_CARRIER_DUTY 0.33F
#define CAMERA_PERIOD_MS 200U
#define RMT_WAIT_TIMEOUT_MS 1000

static const char *TAG = "h2_ir_node";

static rmt_channel_handle_t tx_channel;
static rmt_encoder_handle_t copy_encoder;
static bool tx_fault_latched;

/* RMT borrows its payload until TX finishes. These buffers outlive a timeout.
 * The console task is the only sender. After any TX error no buffer is reused;
 * reboot is required. Future Zigbee senders must use the same serialized owner.
 */
static rmt_symbol_word_t command_symbols[COMMAND_SYMBOL_COUNT];
static const rmt_symbol_word_t camera_burst = {
    .level0 = 1,
    .duration0 = 20000U,
    .level1 = 0,
    .duration1 = 20000U,
};

static rmt_symbol_word_t symbol(uint16_t pulse_us, uint16_t space_us)
{
    rmt_symbol_word_t item = {
        .level0 = 1,
        .duration0 = pulse_us,
        .level1 = 0,
        .duration1 = space_us,
    };
    return item;
}

static esp_err_t ir_tx_init(void)
{
    ESP_RETURN_ON_ERROR(gpio_reset_pin(IR_TX_GPIO), TAG, "reset GPIO%d", IR_TX_GPIO);
    ESP_RETURN_ON_ERROR(gpio_set_direction(IR_TX_GPIO, GPIO_MODE_OUTPUT), TAG, "set GPIO%d output", IR_TX_GPIO);
    ESP_RETURN_ON_ERROR(gpio_set_level(IR_TX_GPIO, 0), TAG, "hold GPIO%d low", IR_TX_GPIO);

    const rmt_tx_channel_config_t channel_config = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .gpio_num = IR_TX_GPIO,
        .mem_block_symbols = 64,
        .resolution_hz = RMT_RESOLUTION_HZ,
        .trans_queue_depth = 4,
        .flags = {
            .invert_out = false,
            .with_dma = false,
            .io_loop_back = false,
            .io_od_mode = false,
        },
    };
    ESP_RETURN_ON_ERROR(rmt_new_tx_channel(&channel_config, &tx_channel), TAG, "create RMT TX");

    const rmt_carrier_config_t carrier_config = {
        .frequency_hz = IR_CARRIER_HZ,
        .duty_cycle = IR_CARRIER_DUTY,
        .flags = {
            .polarity_active_low = false,
            .always_on = false,
        },
    };
    ESP_RETURN_ON_ERROR(rmt_apply_carrier(tx_channel, &carrier_config), TAG, "apply carrier");

    const rmt_copy_encoder_config_t encoder_config = {};
    ESP_RETURN_ON_ERROR(rmt_new_copy_encoder(&encoder_config, &copy_encoder), TAG, "create encoder");
    return rmt_enable(tx_channel);
}

static esp_err_t transmit_symbols(const rmt_symbol_word_t *symbols, size_t symbol_count)
{
    ESP_RETURN_ON_FALSE(!tx_fault_latched, ESP_ERR_INVALID_STATE, TAG,
                       "TX disabled after an error; inspect the board and reboot");
    const rmt_transmit_config_t transmit_config = {
        .loop_count = 0,
        .flags = {
            .eot_level = 0,
            .queue_nonblocking = 0,
        },
    };
    esp_err_t result = rmt_transmit(
        tx_channel,
        copy_encoder,
        symbols,
        symbol_count * sizeof(rmt_symbol_word_t),
        &transmit_config
    );
    if (result == ESP_OK) {
        result = rmt_tx_wait_all_done(tx_channel, RMT_WAIT_TIMEOUT_MS);
    }
    if (result != ESP_OK) {
        tx_fault_latched = true;
        /* A wait timeout is not a cancellation. Stop RMT before returning.
         * Even if stopping fails, payload remains valid and is never reused.
         */
        const esp_err_t stop_result = rmt_disable(tx_channel);
        ESP_LOGE(TAG, "RMT TX failed: %s; stop: %s; further TX blocked until reboot",
                 esp_err_to_name(result), esp_err_to_name(stop_result));
    }
    return result;
}

static size_t append_frame(
    rmt_symbol_word_t *symbols,
    size_t offset,
    const uint8_t frame[FRAME_BYTE_COUNT],
    bool another_frame_follows
)
{
    symbols[offset++] = symbol(LEADER_PULSE_US, LEADER_SPACE_US);

    for (size_t byte_index = 0; byte_index < FRAME_BYTE_COUNT; ++byte_index) {
        for (int shift = 7; shift >= 0; --shift) {
            const bool one = (frame[byte_index] & (1U << shift)) != 0;
            symbols[offset++] = symbol(BIT_PULSE_US, one ? ONE_SPACE_US : ZERO_SPACE_US);
        }
    }

    symbols[offset++] = symbol(
        BIT_PULSE_US,
        another_frame_follows ? INTER_FRAME_SPACE_US : 1U
    );
    return offset;
}

static esp_err_t send_carrier_camera_test(unsigned duration_seconds)
{
    ESP_RETURN_ON_FALSE(!tx_fault_latched, ESP_ERR_INVALID_STATE, TAG,
                       "TX disabled after an error; reboot required");
    const unsigned burst_count = duration_seconds * 1000U / CAMERA_PERIOD_MS;
    ESP_LOGI(TAG, "camera test: nominal %u s, %u short IR bursts on GPIO%d",
             duration_seconds, burst_count, IR_TX_GPIO);
    TickType_t next_period = xTaskGetTickCount();
    for (unsigned index = 0; index < burst_count; ++index) {
        ESP_RETURN_ON_ERROR(transmit_symbols(&camera_burst, 1), TAG, "camera test burst");
        vTaskDelayUntil(&next_period, pdMS_TO_TICKS(CAMERA_PERIOD_MS));
    }
    ESP_LOGI(TAG, "camera test TX complete; optical output requires camera confirmation");
    return ESP_OK;
}

static esp_err_t send_carrier_command(
    const char *command_name,
    const uint8_t frame[FRAME_BYTE_COUNT]
)
{
    /* Check before changing a buffer an earlier failed TX may still reference. */
    ESP_RETURN_ON_FALSE(!tx_fault_latched, ESP_ERR_INVALID_STATE, TAG,
                       "TX disabled after an error; reboot required");
    size_t count = 0;
    for (unsigned index = 0; index < FRAME_REPEAT_COUNT; ++index) {
        count = append_frame(command_symbols, count, frame, index + 1U < FRAME_REPEAT_COUNT);
    }

    ESP_LOGI(TAG, "sending %s: %u frames, %u symbols", command_name, FRAME_REPEAT_COUNT, (unsigned)count);
    const esp_err_t result = transmit_symbols(command_symbols, count);
    if (result == ESP_OK) {
        ESP_LOGI(TAG, "TX complete: %s; appliance response not confirmed", command_name);
    }
    return result;
}

static void print_help(void)
{
    puts("");
    puts("ESP32-H2 IR test commands");
    puts("  c : 2-second camera test (no A/C command)");
    puts("  5 : 5-second camera test (no A/C command)");
    puts("  n : Carrier CS-A061GS power on / cool 17 C / high fan");
    puts("  f : Carrier CS-A061GS power off");
    puts("  h : show this help");
    puts("");
}

void app_main(void)
{
    setvbuf(stdin, NULL, _IONBF, 0);
    setvbuf(stdout, NULL, _IONBF, 0);

    ESP_LOGI(TAG, "booted with ESP-IDF %s", esp_get_idf_version());
    ESP_ERROR_CHECK(ir_tx_init());
    ESP_LOGI(TAG, "IR output configured: GPIO%d, %u Hz, duty %.0f%% (not measured)",
             IR_TX_GPIO, IR_CARRIER_HZ, (double)(IR_CARRIER_DUTY * 100.0F));
    print_help();

    while (true) {
        const int input = getchar();
        if (input == EOF) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }

        switch (tolower(input)) {
        case 'c':
            ESP_ERROR_CHECK_WITHOUT_ABORT(send_carrier_camera_test(2U));
            break;
        case '5':
            ESP_ERROR_CHECK_WITHOUT_ABORT(send_carrier_camera_test(5U));
            break;
        case 'n':
            ESP_ERROR_CHECK_WITHOUT_ABORT(
                send_carrier_command("POWER_ON_COOL_17_HIGH", POWER_ON_COOL_17_HIGH)
            );
            break;
        case 'f':
            ESP_ERROR_CHECK_WITHOUT_ABORT(send_carrier_command("POWER_OFF", POWER_OFF));
            break;
        case 'h':
        case '?':
            print_help();
            break;
        case '\r':
        case '\n':
            break;
        default:
            ESP_LOGW(TAG, "unknown command '%c'; press h for help", input);
            break;
        }
    }
}
