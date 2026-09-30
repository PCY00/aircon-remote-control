#pragma once

#include <stdint.h>

/*
 * Standalone bring-up fixtures for Carrier CS-A061GS.
 * Source of truth: device_profiles/air_conditioner/Carrier/CS-A061GS/commands.json.
 * tests/test_h2_ir_firmware.py checks these fixtures against that profile.
 * Carrier frequency is configured, not measured by the phone-camera test.
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
#define FRAME_SYMBOL_COUNT (1U + (FRAME_BYTE_COUNT * 8U) + 1U)
#define COMMAND_SYMBOL_COUNT (FRAME_SYMBOL_COUNT * FRAME_REPEAT_COUNT)

static const uint8_t POWER_ON_COOL_17_HIGH[FRAME_BYTE_COUNT] = {
    0xB2, 0x4D, 0x3F, 0xC0, 0x00, 0xFF,
};

static const uint8_t POWER_OFF[FRAME_BYTE_COUNT] = {
    0xB2, 0x4D, 0x7B, 0x84, 0xE0, 0x1F,
};
