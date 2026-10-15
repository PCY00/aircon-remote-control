#pragma once

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "ir_protocol.h"

/* Copied from ../esp32-h2-ir-node/main/carrier_profile.h; kept in sync by a host test.
 * Source of truth: device_profiles/air_conditioner/Carrier/CS-A061GS/commands.json.
 */
#define IR_CARRIER_HZ 38000U
#define LEADER_PULSE_US 4350U
#define LEADER_SPACE_US 4350U
#define BIT_PULSE_US 560U
#define ZERO_SPACE_US 520U
#define ONE_SPACE_US 1610U
#define INTER_FRAME_SPACE_US 5150U
#define FRAME_BYTE_COUNT 6U
#define FRAME_REPEAT_COUNT 2U
#define MAX_FRAME_COUNT 3U
#define FRAME_SYMBOL_COUNT (1U + (FRAME_BYTE_COUNT * 8U) + 1U)
#define COMMAND_SYMBOL_COUNT (FRAME_SYMBOL_COUNT * MAX_FRAME_COUNT)

static const uint8_t POWER_OFF[FRAME_BYTE_COUNT] = {
    0xB2, 0x4D, 0x7B, 0x84, 0xE0, 0x1F,
};

static inline bool carrier_command_frames(const aircon_request_t *request,
                                          uint8_t frames[MAX_FRAME_COUNT][FRAME_BYTE_COUNT],
                                          uint8_t *frame_count)
{
    if (request == NULL || frames == NULL || frame_count == NULL) {
        return false;
    }
    static const uint8_t mode_auto[FRAME_BYTE_COUNT] = {0xB2, 0x4D, 0x1F, 0xE0, 0x08, 0xF7};
    static const uint8_t mode_dry[FRAME_BYTE_COUNT] = {0xB2, 0x4D, 0x1F, 0xE0, 0x04, 0xFB};
    static const uint8_t mode_fan[FRAME_BYTE_COUNT] = {0xB2, 0x4D, 0x3F, 0xC0, 0xE4, 0x1B};
    static const uint8_t turbo[FRAME_BYTE_COUNT] = {0xB5, 0x4A, 0xF5, 0x0A, 0xA2, 0x5D};
    static const uint8_t led_toggle[FRAME_BYTE_COUNT] = {0xB5, 0x4A, 0xF5, 0x0A, 0xA5, 0x5A};
    static const uint8_t airflow_fix[FRAME_BYTE_COUNT] = {0xB2, 0x4D, 0x0F, 0xF0, 0xE0, 0x1F};
    static const uint8_t swing_toggle[FRAME_BYTE_COUNT] = {0xB2, 0x4D, 0x6B, 0x94, 0xE0, 0x1F};
    /* Only the eco/sleep command, sent once as in economy-press-01. The captured press
     * also carried the remote's cool 17 C/auto state; the Pi follows with COOL_STATE
     * for the current setpoint.
     */
    static const uint8_t economy[FRAME_BYTE_COUNT] = {0xB2, 0x4D, 0xE0, 0x1F, 0x03, 0xFC};

    const uint8_t *fixed = NULL;
    uint8_t count = FRAME_REPEAT_COUNT;
    switch (request->command_id) {
    case AIRCON_COMMAND_POWER_OFF: fixed = POWER_OFF; break;
    case AIRCON_COMMAND_MODE_AUTO: fixed = mode_auto; break;
    case AIRCON_COMMAND_MODE_DRY: fixed = mode_dry; break;
    case AIRCON_COMMAND_MODE_FAN_ONLY: fixed = mode_fan; break;
    case AIRCON_COMMAND_TURBO: fixed = turbo; break;
    case AIRCON_COMMAND_LED_TOGGLE: fixed = led_toggle; break;
    case AIRCON_COMMAND_AIRFLOW_FIX: fixed = airflow_fix; count = 1U; break;
    case AIRCON_COMMAND_SWING_TOGGLE: fixed = swing_toggle; break;
    case AIRCON_COMMAND_ECONOMY: fixed = economy; count = 1U; break;
    case AIRCON_COMMAND_COOL_STATE: {
        static const uint8_t fans[4][2] = {
            {0xBF, 0x40}, {0x9F, 0x60}, {0x5F, 0xA0}, {0x3F, 0xC0},
        };
        /* Coolix temperature codes for 17..30 C. Not plain Gray code: 27 C is 0x9
         * and 28 C is 0x8; 0xE is the fan-only (no temperature) code.
         */
        static const uint8_t temperature_codes[14] = {
            0x0, 0x1, 0x3, 0x2, 0x6, 0x7, 0x5, 0x4, 0xC, 0xD, 0x9, 0x8, 0xA, 0xB,
        };
        if (request->temperature_c < 17U || request->temperature_c > 30U ||
            request->fan > AIRCON_FAN_HIGH) {
            return false;
        }
        const uint8_t temperature_byte =
            (uint8_t)(temperature_codes[request->temperature_c - 17U] << 4U);
        for (uint8_t i = 0; i < FRAME_REPEAT_COUNT; ++i) {
            frames[i][0] = 0xB2;
            frames[i][1] = 0x4D;
            frames[i][2] = fans[request->fan][0];
            frames[i][3] = fans[request->fan][1];
            frames[i][4] = temperature_byte;
            frames[i][5] = temperature_byte ^ 0xFFU;
        }
        *frame_count = FRAME_REPEAT_COUNT;
        return true;
    }
    default:
        return false;
    }
    for (uint8_t i = 0; i < count; ++i) {
        memcpy(frames[i], fixed, FRAME_BYTE_COUNT);
    }
    *frame_count = count;
    return true;
}
