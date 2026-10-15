#pragma once

#include <stdint.h>

/* Zigbee commissioning retry backoff: 1 s, doubling, capped at 60 s.
 * Retries only restart Zigbee commissioning; they never emit IR.
 */
#define COMMISSIONING_RETRY_MIN_MS 1000U
#define COMMISSIONING_RETRY_MAX_MS 60000U

/* Returns the delay for this retry and advances *next_delay_ms. Reset
 * *next_delay_ms to COMMISSIONING_RETRY_MIN_MS after a successful join.
 */
static inline uint32_t commissioning_retry_delay_ms(uint32_t *next_delay_ms)
{
    uint32_t delay_ms = *next_delay_ms;
    if (delay_ms < COMMISSIONING_RETRY_MIN_MS) {
        delay_ms = COMMISSIONING_RETRY_MIN_MS;
    } else if (delay_ms > COMMISSIONING_RETRY_MAX_MS) {
        delay_ms = COMMISSIONING_RETRY_MAX_MS;
    }
    *next_delay_ms = delay_ms >= COMMISSIONING_RETRY_MAX_MS / 2U
                         ? COMMISSIONING_RETRY_MAX_MS : delay_ms * 2U;
    return delay_ms;
}
