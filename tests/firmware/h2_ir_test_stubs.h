#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Host-side API doubles. Never linked into an ESP-IDF firmware build. */
typedef int esp_err_t;
enum { ESP_OK = 0, ESP_FAIL = -1, ESP_ERR_TIMEOUT = 1, ESP_ERR_INVALID_STATE = 2 };
enum { GPIO_NUM_8 = 8, GPIO_MODE_OUTPUT = 1, RMT_CLK_SRC_DEFAULT = 0 };
typedef void *rmt_channel_handle_t;
typedef void *rmt_encoder_handle_t;
typedef unsigned TickType_t;
typedef struct {
    uint32_t duration0 : 15;
    uint32_t level0 : 1;
    uint32_t duration1 : 15;
    uint32_t level1 : 1;
} rmt_symbol_word_t;
typedef struct {
    int clk_src, gpio_num, mem_block_symbols;
    unsigned resolution_hz, trans_queue_depth;
    struct { bool invert_out, with_dma, io_loop_back, io_od_mode; } flags;
} rmt_tx_channel_config_t;
typedef struct {
    unsigned frequency_hz;
    float duty_cycle;
    struct { bool polarity_active_low, always_on; } flags;
} rmt_carrier_config_t;
typedef struct { int unused; } rmt_copy_encoder_config_t;
typedef struct {
    int loop_count;
    struct { int eot_level, queue_nonblocking; } flags;
} rmt_transmit_config_t;

#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_RETURN_ON_ERROR(expr, ...) do { esp_err_t error_ = (expr); if (error_ != ESP_OK) return error_; } while (0)
#define ESP_RETURN_ON_FALSE(condition, error, ...) do { if (!(condition)) return (error); } while (0)
#define ESP_ERROR_CHECK(expr) ((void)(expr))
#define ESP_ERROR_CHECK_WITHOUT_ABORT(expr) ((void)(expr))
#define pdMS_TO_TICKS(milliseconds) (milliseconds)

static unsigned fake_ticks, fake_transmits, fake_stops;
static bool fake_wait_failure, fake_submit_failure, fake_stop_failure;
static const rmt_symbol_word_t *fake_payload;
static size_t fake_symbol_count;

static esp_err_t gpio_reset_pin(int pin) { return ESP_OK; }
static esp_err_t gpio_set_direction(int pin, int mode) { return ESP_OK; }
static esp_err_t gpio_set_level(int pin, int level) { return ESP_OK; }
static esp_err_t rmt_new_tx_channel(const rmt_tx_channel_config_t *config, rmt_channel_handle_t *out)
{ *out = (void *)1; return ESP_OK; }
static esp_err_t rmt_apply_carrier(rmt_channel_handle_t channel, const rmt_carrier_config_t *config)
{ return ESP_OK; }
static esp_err_t rmt_new_copy_encoder(const rmt_copy_encoder_config_t *config, rmt_encoder_handle_t *out)
{ *out = (void *)1; return ESP_OK; }
static esp_err_t rmt_enable(rmt_channel_handle_t channel) { return ESP_OK; }
static esp_err_t rmt_disable(rmt_channel_handle_t channel)
{ ++fake_stops; return fake_stop_failure ? ESP_FAIL : ESP_OK; }
static const char *esp_get_idf_version(void) { return "host-test"; }
static const char *esp_err_to_name(esp_err_t error) { return "host-test"; }
static TickType_t xTaskGetTickCount(void) { return fake_ticks; }
static void vTaskDelay(unsigned ticks) { fake_ticks += ticks; }
static void vTaskDelayUntil(TickType_t *last_wake, unsigned period)
{ *last_wake += period; if (fake_ticks < *last_wake) fake_ticks = *last_wake; }
static esp_err_t rmt_transmit(rmt_channel_handle_t channel, rmt_encoder_handle_t encoder,
                            const void *payload, size_t bytes, const rmt_transmit_config_t *config)
{
    ++fake_transmits;
    if (fake_submit_failure) return ESP_FAIL;
    fake_payload = payload;
    fake_symbol_count = bytes / sizeof(rmt_symbol_word_t);
    return ESP_OK;
}
static esp_err_t rmt_tx_wait_all_done(rmt_channel_handle_t channel, int timeout_ms)
{
    if (fake_wait_failure) return ESP_ERR_TIMEOUT;
    unsigned duration_us = 0;
    for (size_t index = 0; index < fake_symbol_count; ++index)
        duration_us += fake_payload[index].duration0 + fake_payload[index].duration1;
    fake_ticks += (duration_us + 999U) / 1000U;
    return ESP_OK;
}
