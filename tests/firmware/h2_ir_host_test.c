#include <stdio.h>
#include <string.h>

#include "main.c"

int main(int argc, char **argv)
{
    if (argc != 2 || ir_tx_init() != ESP_OK) return 1;
    esp_err_t result;
    if (strcmp(argv[1], "off") == 0) {
        result = send_carrier_command("POWER_OFF", POWER_OFF);
    } else if (strcmp(argv[1], "on") == 0) {
        result = send_carrier_command("POWER_ON_COOL_17_HIGH", POWER_ON_COOL_17_HIGH);
    } else if (strcmp(argv[1], "camera2") == 0) {
        result = send_carrier_camera_test(2U);
    } else if (strcmp(argv[1], "camera5") == 0) {
        result = send_carrier_camera_test(5U);
    } else {
        fake_submit_failure = strcmp(argv[1], "submit_error") == 0;
        fake_stop_failure = strcmp(argv[1], "stop_error") == 0;
        fake_wait_failure = !fake_submit_failure;
        result = send_carrier_command("POWER_OFF", POWER_OFF);
        if (result == ESP_OK || !tx_fault_latched || fake_stops != 1) return 2;
        rmt_symbol_word_t preserved[COMMAND_SYMBOL_COUNT];
        memcpy(preserved, command_symbols, sizeof(preserved));
        const unsigned previous_transmits = fake_transmits;
        if (send_carrier_command("POWER_ON_COOL_17_HIGH", POWER_ON_COOL_17_HIGH) != ESP_ERR_INVALID_STATE)
            return 3;
        if (memcmp(preserved, command_symbols, sizeof(preserved)) != 0) return 4;
        if (send_carrier_camera_test(2U) != ESP_ERR_INVALID_STATE) return 5;
        if (fake_transmits != previous_transmits) return 6;
        /* A failed driver stop must not permit reuse of the borrowed payload. */
        if (fake_payload && memcmp(preserved, fake_payload, sizeof(preserved)) != 0) return 7;
    }
    printf("{\"result\":%d,\"ticks\":%u,\"transmits\":%u,\"stops\":%u,\"carrier_hz\":%u,\"symbols\":[",
           result, fake_ticks, fake_transmits, fake_stops, IR_CARRIER_HZ);
    for (size_t index = 0; index < fake_symbol_count; ++index) {
        const rmt_symbol_word_t item = fake_payload[index];
        if (item.level0 != 1 || item.level1 != 0) return 8;
        printf("%s[%u,%u]", index ? "," : "", item.duration0, item.duration1);
    }
    puts("]}");
    return 0;
}
