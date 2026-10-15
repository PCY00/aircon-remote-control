#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "ir_protocol.h"

/* Who may command IR and how fast it may go out. Pure helpers only, so
 * tests/firmware/h2_zigbee_protocol_test.c can check them on the host.
 */

/* Mirrors ezb_addr_mode_e; main.c static-asserts these against the SDK. */
#define AIRCON_ADDR_MODE_NONE 0U
#define AIRCON_ADDR_MODE_GROUP 1U
#define AIRCON_ADDR_MODE_SHORT 2U
#define AIRCON_ADDR_MODE_EXT 3U
/* The Zigbee coordinator (Zigbee2MQTT on the Pi) always has short address 0x0000. */
#define AIRCON_COORDINATOR_SHORT_ADDR 0x0000U
#define AIRCON_REJECT_LOG_INTERVAL_MS 60000U

/* Minimum idle time from the end of one IR transmission to the start of the
 * next, chosen by the command about to be sent. Appliance-state commands
 * (POWER_OFF, COOL_STATE, MODE_*, ECONOMY) wait 2 s so a burst of accepted
 * requests cannot cycle the air conditioner; feature toggles may follow after
 * 0.5 s. The gap is measured from the previous transmission's completion.
 */
#define IR_PACING_STATE_GAP_MS 2000U
#define IR_PACING_FEATURE_GAP_MS 500U

/* True only for a short (16-bit) source address equal to the coordinator's.
 * An extended source must be resolved to its short address first; group and
 * absent addresses are never accepted.
 */
static inline bool aircon_source_is_coordinator(uint8_t addr_mode, uint16_t short_addr)
{
    return addr_mode == AIRCON_ADDR_MODE_SHORT && short_addr == AIRCON_COORDINATOR_SHORT_ADDR;
}

/* The first rejection is logged; later ones at most once per minute. The
 * millisecond clock may wrap; the subtraction is wrap-safe.
 */
static inline bool aircon_reject_log_due(bool logged_before, uint32_t last_log_ms,
                                         uint32_t now_ms)
{
    return !logged_before || now_ms - last_log_ms >= AIRCON_REJECT_LOG_INTERVAL_MS;
}

static inline uint32_t ir_pacing_gap_ms(uint8_t command_id)
{
    switch (command_id) {
    case AIRCON_COMMAND_TURBO:
    case AIRCON_COMMAND_LED_TOGGLE:
    case AIRCON_COMMAND_AIRFLOW_FIX:
    case AIRCON_COMMAND_SWING_TOGGLE:
        return IR_PACING_FEATURE_GAP_MS;
    default:
        /* Appliance-state commands, and anything unknown, get the long gap. */
        return IR_PACING_STATE_GAP_MS;
    }
}

/* Milliseconds to wait before transmitting command_id when the previous
 * transmission ended at last_tx_ms; 0 before the first transmission.
 */
static inline uint32_t ir_pacing_delay_ms(bool have_last_tx, uint32_t last_tx_ms,
                                          uint8_t command_id, uint32_t now_ms)
{
    if (!have_last_tx) {
        return 0U;
    }
    const uint32_t gap_ms = ir_pacing_gap_ms(command_id);
    const uint32_t elapsed_ms = now_ms - last_tx_ms;
    return elapsed_ms >= gap_ms ? 0U : gap_ms - elapsed_ms;
}
