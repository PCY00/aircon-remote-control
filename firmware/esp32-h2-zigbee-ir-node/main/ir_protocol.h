#pragma once

#include <stdbool.h>
#include <stdint.h>

/* Private application cluster, not a registered manufacturer ID. */
#define AIRCON_CLUSTER_ID 0xFF00U
#define AIRCON_ENDPOINT 10U
#define AIRCON_ZCL_SEND_COMMAND 0x00U
#define AIRCON_ZCL_RESULT_COMMAND 0x01U
#define AIRCON_ZCL_SEND_V2_COMMAND 0x02U
#define AIRCON_WIRE_VERSION_V1 1U
#define AIRCON_WIRE_VERSION_V2 2U
#define AIRCON_PROFILE_CARRIER_CS_A061GS 1U
#define AIRCON_COMMAND_POWER_OFF 1U
#define AIRCON_COMMAND_COOL_STATE 2U
#define AIRCON_COMMAND_MODE_AUTO 3U
#define AIRCON_COMMAND_MODE_DRY 4U
#define AIRCON_COMMAND_MODE_FAN_ONLY 5U
#define AIRCON_COMMAND_ECONOMY 6U
#define AIRCON_COMMAND_TURBO 7U
#define AIRCON_COMMAND_LED_TOGGLE 8U
#define AIRCON_COMMAND_AIRFLOW_FIX 9U
#define AIRCON_COMMAND_SWING_TOGGLE 10U
#define AIRCON_FAN_AUTO 0U
#define AIRCON_FAN_LOW 1U
#define AIRCON_FAN_MEDIUM 2U
#define AIRCON_FAN_HIGH 3U
#define AIRCON_REQUEST_V1_SIZE 6U
#define AIRCON_REQUEST_V2_SIZE 8U
#define AIRCON_RESULT_SIZE 7U

typedef struct {
    uint8_t wire_version;
    uint8_t command_id;
    uint8_t temperature_c;
    uint8_t fan;
    uint32_t request_id;
} aircon_request_t;

typedef enum {
    AIRCON_RESULT_ACCEPTED = 0,
    AIRCON_RESULT_SENT = 1,
    AIRCON_RESULT_FAILED = 2,
    AIRCON_RESULT_DUPLICATE = 3,
    AIRCON_RESULT_BUSY = 4,
} aircon_result_t;

static inline bool aircon_decode_request(const uint8_t *payload, uint16_t length,
                                         aircon_request_t *request)
{
    if (payload == NULL || request == NULL ||
        (length != AIRCON_REQUEST_V1_SIZE && length != AIRCON_REQUEST_V2_SIZE) ||
        payload[1] != AIRCON_PROFILE_CARRIER_CS_A061GS) {
        return false;
    }
    if (length == AIRCON_REQUEST_V1_SIZE && payload[0] == AIRCON_WIRE_VERSION_V1) {
        if (payload[2] != AIRCON_COMMAND_POWER_OFF) {
            return false;
        }
        request->temperature_c = 0U;
        request->fan = 0U;
        request->request_id = (uint32_t)payload[3] | ((uint32_t)payload[4] << 8U) |
                              ((uint32_t)payload[5] << 16U);
    } else if (length == AIRCON_REQUEST_V2_SIZE && payload[0] == AIRCON_WIRE_VERSION_V2) {
        request->temperature_c = payload[3];
        request->fan = payload[4];
        if (payload[2] == AIRCON_COMMAND_COOL_STATE) {
            if (request->temperature_c < 17U || request->temperature_c > 30U ||
                request->fan > AIRCON_FAN_HIGH) {
                return false;
            }
        } else if (payload[2] < AIRCON_COMMAND_POWER_OFF ||
                   payload[2] > AIRCON_COMMAND_SWING_TOGGLE ||
                   request->temperature_c != 0U || request->fan != 0U) {
            return false;
        }
        request->request_id = (uint32_t)payload[5] | ((uint32_t)payload[6] << 8U) |
                              ((uint32_t)payload[7] << 16U);
    } else {
        return false;
    }
    request->wire_version = payload[0];
    request->command_id = payload[2];
    return request->request_id != 0U;
}

static inline void aircon_encode_result(uint8_t payload[AIRCON_RESULT_SIZE],
                                        const aircon_request_t *request, aircon_result_t result)
{
    payload[0] = request->wire_version;
    payload[1] = AIRCON_PROFILE_CARRIER_CS_A061GS;
    payload[2] = request->command_id;
    payload[3] = (uint8_t)(request->request_id & 0xffU);
    payload[4] = (uint8_t)((request->request_id >> 8U) & 0xffU);
    payload[5] = (uint8_t)((request->request_id >> 16U) & 0xffU);
    payload[6] = (uint8_t)result;
}
