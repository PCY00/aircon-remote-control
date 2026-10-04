#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "esp_check.h"
#include "esp_log.h"
#include "carrier_profile.h"
#include "ir_tx.h"

#define IR_TX_GPIO GPIO_NUM_5
#define RMT_RESOLUTION_HZ 1000000U
#define RMT_WAIT_TIMEOUT_MS 1000

static const char *TAG = "aircon_ir";
static rmt_channel_handle_t tx_channel;
static rmt_encoder_handle_t copy_encoder;
static bool tx_fault_latched;
/* RMT borrows the payload until TX completes. A failure latches and prevents
 * reuse of this buffer, even if disabling the channel also fails. Only the IR
 * worker task calls this module.
 */
static rmt_symbol_word_t command_symbols[COMMAND_SYMBOL_COUNT];

static rmt_symbol_word_t make_symbol(uint16_t pulse_us, uint16_t space_us)
{
    return (rmt_symbol_word_t){
        .level0 = 1, .duration0 = pulse_us,
        .level1 = 0, .duration1 = space_us,
    };
}

esp_err_t aircon_ir_init(void)
{
    ESP_RETURN_ON_ERROR(gpio_reset_pin(IR_TX_GPIO), TAG, "reset GPIO5");
    ESP_RETURN_ON_ERROR(gpio_set_direction(IR_TX_GPIO, GPIO_MODE_OUTPUT), TAG, "set GPIO5 output");
    ESP_RETURN_ON_ERROR(gpio_set_level(IR_TX_GPIO, 0), TAG, "hold GPIO5 low");

    const rmt_tx_channel_config_t channel_config = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .gpio_num = IR_TX_GPIO,
        .mem_block_symbols = 64,
        .resolution_hz = RMT_RESOLUTION_HZ,
        .trans_queue_depth = 4,
        .flags = {.invert_out = false, .with_dma = false,
                  .io_loop_back = false, .io_od_mode = false},
    };
    ESP_RETURN_ON_ERROR(rmt_new_tx_channel(&channel_config, &tx_channel), TAG, "create RMT TX");
    const rmt_carrier_config_t carrier_config = {
        .frequency_hz = IR_CARRIER_HZ,
        .duty_cycle = 0.33F,
        .flags = {.polarity_active_low = false, .always_on = false},
    };
    ESP_RETURN_ON_ERROR(rmt_apply_carrier(tx_channel, &carrier_config), TAG, "apply carrier");
    const rmt_copy_encoder_config_t encoder_config = {};
    ESP_RETURN_ON_ERROR(rmt_new_copy_encoder(&encoder_config, &copy_encoder), TAG, "create encoder");
    return rmt_enable(tx_channel);
}

esp_err_t aircon_ir_send(const aircon_request_t *request)
{
    ESP_RETURN_ON_FALSE(!tx_fault_latched, ESP_ERR_INVALID_STATE, TAG,
                        "RMT failed before; reboot required");
    uint8_t frames[MAX_FRAME_COUNT][FRAME_BYTE_COUNT] = {0};
    uint8_t frame_count = 0;
    ESP_RETURN_ON_FALSE(carrier_command_frames(request, frames, &frame_count),
                        ESP_ERR_INVALID_ARG, TAG, "unsupported Carrier IR request");
    size_t count = 0;
    for (uint8_t frame = 0; frame < frame_count; ++frame) {
        command_symbols[count++] = make_symbol(LEADER_PULSE_US, LEADER_SPACE_US);
        for (size_t byte = 0; byte < FRAME_BYTE_COUNT; ++byte) {
            for (int bit = 7; bit >= 0; --bit) {
                const bool one = (frames[frame][byte] & (1U << bit)) != 0;
                command_symbols[count++] = make_symbol(BIT_PULSE_US, one ? ONE_SPACE_US : ZERO_SPACE_US);
            }
        }
        command_symbols[count++] = make_symbol(BIT_PULSE_US,
                                               frame + 1U < frame_count ? INTER_FRAME_SPACE_US : 1U);
    }
    const rmt_transmit_config_t transmit_config = {
        .loop_count = 0,
        .flags = {.eot_level = 0, .queue_nonblocking = 0},
    };
    esp_err_t result = rmt_transmit(tx_channel, copy_encoder, command_symbols,
                                    count * sizeof(rmt_symbol_word_t), &transmit_config);
    if (result == ESP_OK) {
        result = rmt_tx_wait_all_done(tx_channel, RMT_WAIT_TIMEOUT_MS);
    }
    if (result != ESP_OK) {
        tx_fault_latched = true;
        const esp_err_t stop_result = rmt_disable(tx_channel);
        ESP_LOGE(TAG, "RMT failed: %s; stop: %s; further TX blocked until reboot",
                 esp_err_to_name(result), esp_err_to_name(stop_result));
    }
    return result;
}
