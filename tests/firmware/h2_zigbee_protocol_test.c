#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "carrier_profile.h"
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
    static const uint8_t economy[3][6] = {
        {0xB2, 0x4D, 0xE0, 0x1F, 0x03, 0xFC},
        {0xB2, 0x4D, 0xBF, 0x40, 0x00, 0xFF},
        {0xB2, 0x4D, 0xBF, 0x40, 0x00, 0xFF},
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
    expect_frames(AIRCON_COMMAND_ECONOMY, &economy[0][0], 3);
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
