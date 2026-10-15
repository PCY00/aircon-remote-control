#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "carrier_profile.h"
#include "command_policy.h"
#include "commissioning_retry.h"
#include "ir_protocol.h"

static void expect_frames(uint8_t command, const uint8_t *expected,
                          uint8_t expected_count)
{
    const aircon_request_t request = {
        .wire_version = AIRCON_WIRE_VERSION_V2, .command_id = command,
        .request_id = 0x123456U,
    };
    uint8_t frames[MAX_FRAME_COUNT][FRAME_BYTE_COUNT] = {0};
    uint8_t count = 0;
    assert(carrier_command_frames(&request, frames, &count));
    assert(count == expected_count);
    assert(memcmp(frames, expected, (size_t)count * FRAME_BYTE_COUNT) == 0);
}

static void expect_cool_frames(uint8_t temperature, uint8_t fan, const uint8_t *expected)
{
    const aircon_request_t request = {
        .wire_version = AIRCON_WIRE_VERSION_V2, .command_id = AIRCON_COMMAND_COOL_STATE,
        .temperature_c = temperature, .fan = fan, .request_id = 1U,
    };
    uint8_t frames[MAX_FRAME_COUNT][FRAME_BYTE_COUNT] = {0};
    uint8_t count = 0;
    assert(carrier_command_frames(&request, frames, &count));
    assert(count == FRAME_REPEAT_COUNT);
    assert(memcmp(frames, expected, (size_t)count * FRAME_BYTE_COUNT) == 0);
}

static void print_profile_frames(uint8_t command, uint8_t temperature, uint8_t fan)
{
    const aircon_request_t request = {
        .wire_version = AIRCON_WIRE_VERSION_V2,
        .command_id = command,
        .temperature_c = temperature,
        .fan = fan,
        .request_id = 1U,
    };
    uint8_t frames[MAX_FRAME_COUNT][FRAME_BYTE_COUNT] = {0};
    uint8_t count = 0;
    assert(carrier_command_frames(&request, frames, &count));
    printf("FRAME %u %u %u %u", command, temperature, fan, count);
    for (uint8_t i = 0; i < count; ++i) {
        printf(" ");
        for (uint8_t byte = 0; byte < FRAME_BYTE_COUNT; ++byte) {
            printf("%02x", frames[i][byte]);
        }
    }
    printf("\n");
}

int main(void)
{
    aircon_request_t request = {0};
    uint8_t legacy[AIRCON_REQUEST_V1_SIZE] = {1, 1, 1, 0x56, 0x34, 0x12};
    assert(aircon_decode_request(legacy, sizeof(legacy), &request));
    assert(request.wire_version == AIRCON_WIRE_VERSION_V1);
    assert(request.command_id == AIRCON_COMMAND_POWER_OFF);
    assert(request.request_id == 0x123456U);

    uint8_t v2[AIRCON_REQUEST_V2_SIZE] = {2, 1, AIRCON_COMMAND_COOL_STATE,
                                          20, AIRCON_FAN_HIGH, 0x56, 0x34, 0x12};
    assert(aircon_decode_request(v2, sizeof(v2), &request));
    assert(request.wire_version == AIRCON_WIRE_VERSION_V2);
    assert(request.temperature_c == 20 && request.fan == AIRCON_FAN_HIGH);
    assert(request.request_id == 0x123456U);

    uint8_t result[AIRCON_RESULT_SIZE] = {0};
    aircon_encode_result(result, &request, AIRCON_RESULT_SENT);
    assert(result[0] == 2 && result[1] == 1 && result[2] == AIRCON_COMMAND_COOL_STATE);
    assert(result[3] == 0x56 && result[4] == 0x34 && result[5] == 0x12);
    assert(result[6] == AIRCON_RESULT_SENT);

    assert(!aircon_decode_request(v2, sizeof(v2) - 1U, &request));
    assert(!aircon_decode_request(v2, 1U, &request));
    v2[0] = 3;
    assert(!aircon_decode_request(v2, sizeof(v2), &request));
    v2[0] = 2;
    v2[1] = 2;
    assert(!aircon_decode_request(v2, sizeof(v2), &request));
    v2[1] = 1;
    v2[3] = 16;
    assert(!aircon_decode_request(v2, sizeof(v2), &request));
    v2[3] = 31;
    assert(!aircon_decode_request(v2, sizeof(v2), &request));
    v2[3] = 20;
    v2[4] = 4;
    assert(!aircon_decode_request(v2, sizeof(v2), &request));
    v2[4] = AIRCON_FAN_HIGH;
    v2[2] = AIRCON_COMMAND_POWER_OFF;
    assert(!aircon_decode_request(v2, sizeof(v2), &request));
    v2[3] = 0;
    v2[4] = 0;
    assert(aircon_decode_request(v2, sizeof(v2), &request));
    v2[2] = 11;
    assert(!aircon_decode_request(v2, sizeof(v2), &request));
    v2[2] = AIRCON_COMMAND_POWER_OFF;
    v2[5] = v2[6] = v2[7] = 0;
    assert(!aircon_decode_request(v2, sizeof(v2), &request));
    assert(!aircon_decode_request(NULL, sizeof(v2), &request));

    legacy[2] = AIRCON_COMMAND_COOL_STATE;
    assert(!aircon_decode_request(legacy, sizeof(legacy), &request));

    static const uint8_t off[2][6] = {
        {0xB2, 0x4D, 0x7B, 0x84, 0xE0, 0x1F},
        {0xB2, 0x4D, 0x7B, 0x84, 0xE0, 0x1F},
    };
    static const uint8_t auto_mode[2][6] = {
        {0xB2, 0x4D, 0x1F, 0xE0, 0x08, 0xF7},
        {0xB2, 0x4D, 0x1F, 0xE0, 0x08, 0xF7},
    };
    static const uint8_t dry[2][6] = {
        {0xB2, 0x4D, 0x1F, 0xE0, 0x04, 0xFB},
        {0xB2, 0x4D, 0x1F, 0xE0, 0x04, 0xFB},
    };
    static const uint8_t fan_only[2][6] = {
        {0xB2, 0x4D, 0x3F, 0xC0, 0xE4, 0x1B},
        {0xB2, 0x4D, 0x3F, 0xC0, 0xE4, 0x1B},
    };
    /* Eco/sleep only, once as captured: no cool 17 C/auto state frame is replayed. */
    static const uint8_t economy[1][6] = {
        {0xB2, 0x4D, 0xE0, 0x1F, 0x03, 0xFC},
    };
    static const uint8_t turbo[2][6] = {
        {0xB5, 0x4A, 0xF5, 0x0A, 0xA2, 0x5D},
        {0xB5, 0x4A, 0xF5, 0x0A, 0xA2, 0x5D},
    };
    static const uint8_t led[2][6] = {
        {0xB5, 0x4A, 0xF5, 0x0A, 0xA5, 0x5A},
        {0xB5, 0x4A, 0xF5, 0x0A, 0xA5, 0x5A},
    };
    static const uint8_t airflow[1][6] = {
        {0xB2, 0x4D, 0x0F, 0xF0, 0xE0, 0x1F},
    };
    static const uint8_t swing[2][6] = {
        {0xB2, 0x4D, 0x6B, 0x94, 0xE0, 0x1F},
        {0xB2, 0x4D, 0x6B, 0x94, 0xE0, 0x1F},
    };
    expect_frames(AIRCON_COMMAND_POWER_OFF, &off[0][0], 2);
    expect_frames(AIRCON_COMMAND_MODE_AUTO, &auto_mode[0][0], 2);
    expect_frames(AIRCON_COMMAND_MODE_DRY, &dry[0][0], 2);
    expect_frames(AIRCON_COMMAND_MODE_FAN_ONLY, &fan_only[0][0], 2);
    expect_frames(AIRCON_COMMAND_ECONOMY, &economy[0][0], 1);
    expect_frames(AIRCON_COMMAND_TURBO, &turbo[0][0], 2);
    expect_frames(AIRCON_COMMAND_LED_TOGGLE, &led[0][0], 2);
    expect_frames(AIRCON_COMMAND_AIRFLOW_FIX, &airflow[0][0], 1);
    expect_frames(AIRCON_COMMAND_SWING_TOGGLE, &swing[0][0], 2);

    static const uint8_t cool_20_high[2][6] = {
        {0xB2, 0x4D, 0x3F, 0xC0, 0x20, 0xDF},
        {0xB2, 0x4D, 0x3F, 0xC0, 0x20, 0xDF},
    };
    const aircon_request_t cool_request = {
        .wire_version = 2, .command_id = AIRCON_COMMAND_COOL_STATE,
        .temperature_c = 20, .fan = AIRCON_FAN_HIGH, .request_id = 1,
    };
    uint8_t frames[MAX_FRAME_COUNT][FRAME_BYTE_COUNT] = {0};
    uint8_t count = 0;
    assert(carrier_command_frames(&cool_request, frames, &count));
    assert(count == 2);
    assert(memcmp(frames, cool_20_high, sizeof(cool_20_high)) == 0);

    /* Coolix temperature table, not plain Gray code, at 27 and 28 C. */
    static const uint8_t cool_27_auto[2][6] = {
        {0xB2, 0x4D, 0xBF, 0x40, 0x90, 0x6F},
        {0xB2, 0x4D, 0xBF, 0x40, 0x90, 0x6F},
    };
    static const uint8_t cool_28_auto[2][6] = {
        {0xB2, 0x4D, 0xBF, 0x40, 0x80, 0x7F},
        {0xB2, 0x4D, 0xBF, 0x40, 0x80, 0x7F},
    };
    expect_cool_frames(27, AIRCON_FAN_AUTO, &cool_27_auto[0][0]);
    expect_cool_frames(28, AIRCON_FAN_AUTO, &cool_28_auto[0][0]);
    static const uint8_t coolix_codes[14] = {
        0x0, 0x1, 0x3, 0x2, 0x6, 0x7, 0x5, 0x4, 0xC, 0xD, 0x9, 0x8, 0xA, 0xB,
    };
    for (uint8_t temperature = 17U; temperature <= 30U; ++temperature) {
        for (uint8_t fan = AIRCON_FAN_AUTO; fan <= AIRCON_FAN_HIGH; ++fan) {
            const aircon_request_t cool = {
                .wire_version = 2, .command_id = AIRCON_COMMAND_COOL_STATE,
                .temperature_c = temperature, .fan = fan, .request_id = 1,
            };
            assert(carrier_command_frames(&cool, frames, &count));
            assert(count == FRAME_REPEAT_COUNT);
            for (uint8_t i = 0; i < count; ++i) {
                /* 0xE is the fan-only (no temperature) nibble. */
                assert((frames[i][4] >> 4U) != 0xEU);
                assert((frames[i][4] >> 4U) == coolix_codes[temperature - 17U]);
                assert((frames[i][4] & 0x0FU) == 0U);
                assert((uint8_t)(frames[i][4] ^ frames[i][5]) == 0xFFU);
            }
        }
    }

    /* ECONOMY must not carry any cool-state frame (fan byte BF/9F/5F/3F). */
    const aircon_request_t economy_request = {
        .wire_version = 2, .command_id = AIRCON_COMMAND_ECONOMY, .request_id = 1,
    };
    assert(carrier_command_frames(&economy_request, frames, &count));
    for (uint8_t i = 0; i < count; ++i) {
        assert(frames[i][2] != 0xBF && frames[i][2] != 0x9F &&
               frames[i][2] != 0x5F && frames[i][2] != 0x3F);
    }

    /* Commissioning retry backoff: 1 s doubling to a 60 s cap, reset on success. */
    static const uint32_t expected_delays[] = {
        1000U, 2000U, 4000U, 8000U, 16000U, 32000U, 60000U, 60000U,
    };
    uint32_t next_delay_ms = COMMISSIONING_RETRY_MIN_MS;
    for (size_t i = 0; i < sizeof(expected_delays) / sizeof(expected_delays[0]); ++i) {
        assert(commissioning_retry_delay_ms(&next_delay_ms) == expected_delays[i]);
    }
    next_delay_ms = COMMISSIONING_RETRY_MIN_MS;
    assert(commissioning_retry_delay_ms(&next_delay_ms) == 1000U);
    next_delay_ms = 0U;
    assert(commissioning_retry_delay_ms(&next_delay_ms) == 1000U);
    next_delay_ms = UINT32_MAX;
    assert(commissioning_retry_delay_ms(&next_delay_ms) == 60000U);
    assert(next_delay_ms == 60000U);

    /* Coordinator-only source check: short address 0x0000 in short mode only. */
    assert(aircon_source_is_coordinator(AIRCON_ADDR_MODE_SHORT, 0x0000U));
    assert(!aircon_source_is_coordinator(AIRCON_ADDR_MODE_NONE, 0x0000U));
    assert(!aircon_source_is_coordinator(AIRCON_ADDR_MODE_GROUP, 0x0000U));
    /* An extended address must be resolved to a short one before the check. */
    assert(!aircon_source_is_coordinator(AIRCON_ADDR_MODE_EXT, 0x0000U));
    for (unsigned mode = AIRCON_ADDR_MODE_EXT + 1U; mode < 256U; ++mode) {
        assert(!aircon_source_is_coordinator((uint8_t)mode, 0x0000U));
    }
    for (uint32_t short_addr = 1U; short_addr <= 0xFFFFU; ++short_addr) {
        assert(!aircon_source_is_coordinator(AIRCON_ADDR_MODE_SHORT, (uint16_t)short_addr));
    }

    /* Rejection log: first time, then at most once per minute, wrap-safe. */
    assert(aircon_reject_log_due(false, 0U, 0U));
    assert(aircon_reject_log_due(false, 123U, 0U));
    assert(!aircon_reject_log_due(true, 1000U, 1000U));
    assert(!aircon_reject_log_due(true, 1000U, 60999U));
    assert(aircon_reject_log_due(true, 1000U, 61000U));
    assert(aircon_reject_log_due(true, UINT32_MAX - 10U, 59989U));
    assert(!aircon_reject_log_due(true, UINT32_MAX - 10U, 59988U));

    /* IR pacing: 2 s before appliance-state commands, 0.5 s before feature toggles. */
    static const uint8_t state_commands[] = {
        AIRCON_COMMAND_POWER_OFF, AIRCON_COMMAND_COOL_STATE, AIRCON_COMMAND_MODE_AUTO,
        AIRCON_COMMAND_MODE_DRY, AIRCON_COMMAND_MODE_FAN_ONLY, AIRCON_COMMAND_ECONOMY,
    };
    static const uint8_t feature_commands[] = {
        AIRCON_COMMAND_TURBO, AIRCON_COMMAND_LED_TOGGLE, AIRCON_COMMAND_AIRFLOW_FIX,
        AIRCON_COMMAND_SWING_TOGGLE,
    };
    for (size_t i = 0; i < sizeof(state_commands); ++i) {
        assert(ir_pacing_gap_ms(state_commands[i]) == 2000U);
        assert(ir_pacing_delay_ms(false, 0U, state_commands[i], 0U) == 0U);
        assert(ir_pacing_delay_ms(false, 5000U, state_commands[i], 5001U) == 0U);
        assert(ir_pacing_delay_ms(true, 1000U, state_commands[i], 1000U) == 2000U);
        assert(ir_pacing_delay_ms(true, 1000U, state_commands[i], 1500U) == 1500U);
        assert(ir_pacing_delay_ms(true, 1000U, state_commands[i], 2999U) == 1U);
        assert(ir_pacing_delay_ms(true, 1000U, state_commands[i], 3000U) == 0U);
        assert(ir_pacing_delay_ms(true, 1000U, state_commands[i], 90000U) == 0U);
    }
    for (size_t i = 0; i < sizeof(feature_commands); ++i) {
        assert(ir_pacing_gap_ms(feature_commands[i]) == 500U);
        assert(ir_pacing_delay_ms(false, 0U, feature_commands[i], 0U) == 0U);
        assert(ir_pacing_delay_ms(true, 1000U, feature_commands[i], 1000U) == 500U);
        assert(ir_pacing_delay_ms(true, 1000U, feature_commands[i], 1200U) == 300U);
        assert(ir_pacing_delay_ms(true, 1000U, feature_commands[i], 1499U) == 1U);
        assert(ir_pacing_delay_ms(true, 1000U, feature_commands[i], 1500U) == 0U);
    }
    assert(sizeof(state_commands) + sizeof(feature_commands) == AIRCON_COMMAND_SWING_TOGGLE);
    /* Unknown command ids never get the short gap. */
    assert(ir_pacing_gap_ms(0U) == 2000U);
    assert(ir_pacing_gap_ms(AIRCON_COMMAND_SWING_TOGGLE + 1U) == 2000U);
    assert(ir_pacing_gap_ms(255U) == 2000U);
    /* Millisecond clock wrap: 272 ms elapsed across the wrap. */
    assert(ir_pacing_delay_ms(true, 0xFFFFFF00U, AIRCON_COMMAND_POWER_OFF, 0x00000010U) == 1728U);
    assert(ir_pacing_delay_ms(true, 0xFFFFFF00U, AIRCON_COMMAND_SWING_TOGGLE, 0x00000010U) == 228U);
    /* A back-to-back queue keeps appliance-state commands >= 2 s apart however
     * feature toggles are interleaved; the worker restamps after each TX.
     */
    {
        static const uint8_t burst[] = {
            AIRCON_COMMAND_POWER_OFF, AIRCON_COMMAND_SWING_TOGGLE, AIRCON_COMMAND_COOL_STATE,
            AIRCON_COMMAND_TURBO, AIRCON_COMMAND_LED_TOGGLE, AIRCON_COMMAND_POWER_OFF,
            AIRCON_COMMAND_ECONOMY, AIRCON_COMMAND_COOL_STATE, AIRCON_COMMAND_AIRFLOW_FIX,
            AIRCON_COMMAND_MODE_DRY,
        };
        const uint32_t tx_duration_ms = 150U;
        uint32_t now_ms = 10U;
        uint32_t last_tx_ms = 0U;
        uint32_t last_state_start_ms = 0U;
        bool have_last_tx = false;
        bool have_state_tx = false;
        unsigned state_count = 0;
        for (size_t i = 0; i < sizeof(burst); ++i) {
            now_ms += ir_pacing_delay_ms(have_last_tx, last_tx_ms, burst[i], now_ms);
            assert(ir_pacing_delay_ms(have_last_tx, last_tx_ms, burst[i], now_ms) == 0U);
            if (ir_pacing_gap_ms(burst[i]) == IR_PACING_STATE_GAP_MS) {
                assert(!have_state_tx || now_ms - last_state_start_ms >= 2000U + tx_duration_ms);
                have_state_tx = true;
                last_state_start_ms = now_ms;
                ++state_count;
            } else {
                assert(now_ms - last_tx_ms >= 500U);
            }
            now_ms += tx_duration_ms;
            last_tx_ms = now_ms;
            have_last_tx = true;
        }
        assert(state_count == 6U);
        /* Six state commands need at least five 2 s gaps plus their own TX time. */
        assert(now_ms - 10U >= 5U * 2000U + sizeof(burst) * tx_duration_ms);
    }
    printf("POLICY state_gap_ms=%u feature_gap_ms=%u reject_log_ms=%u\n",
           (unsigned)IR_PACING_STATE_GAP_MS, (unsigned)IR_PACING_FEATURE_GAP_MS,
           (unsigned)AIRCON_REJECT_LOG_INTERVAL_MS);

    for (uint8_t command = AIRCON_COMMAND_POWER_OFF;
         command <= AIRCON_COMMAND_SWING_TOGGLE; ++command) {
        if (command != AIRCON_COMMAND_COOL_STATE) {
            print_profile_frames(command, 0U, 0U);
        }
    }
    for (uint8_t temperature = 17U; temperature <= 30U; ++temperature) {
        for (uint8_t fan = AIRCON_FAN_AUTO; fan <= AIRCON_FAN_HIGH; ++fan) {
            print_profile_frames(AIRCON_COMMAND_COOL_STATE, temperature, fan);
        }
    }

    puts("zigbee IR protocol: all checks passed");
    return 0;
}
