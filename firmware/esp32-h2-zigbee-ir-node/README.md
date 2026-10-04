# ESP32-H2 Zigbee IR prototype (basic command firmware)

This is a separate Zigbee firmware project. The validated USB-console test
firmware source under `../esp32-h2-ir-node/` is preserved. At the user's
explicit request on 2026-10-03, the physical COM6 board was flashed with this
Zigbee build; the previous full 4MB flash image was backed up outside the
repository. The local source is the source of truth; `C:\esp` is only an
ASCII-path build staging area on Windows.

The scope is USB-powered ESP32-H2 SuperMini, GPIO5 IR output, and the Carrier
CS-A061GS captured command profile. There is no automatic IR transmission on
startup or network join. The 38 kHz carrier is configured, not instrument-
measured. Firmware reports RMT completion, not measured A/C state. Only
`POWER_OFF` has been physically confirmed on this Zigbee path; the other basic
commands require dashboard/air-conditioner checks.

## Build (no device changes)

```powershell
./scripts/esp32_h2_firmware.ps1 -Action build -Variant zigbee-ir-node
```

Uses ESP-IDF 5.5.4 and pinned `espressif/esp-zigbee-lib` 2.0.4. The helper
prints the staging directory. It copies source files before every build; do
not edit the staging directory. Run the host protocol checks with
`python -m pytest tests/test_h2_zigbee_protocol.py`.
The 2026-10-03 4MB local build passed (binary `0x7c930` bytes, 47% of the app
partition free). Flash hash verification and the first boot succeeded; the
first network steering returned `EZB_BDB_STATUS_NO_NETWORK` (`0x03`). A later
120-second permit-join window succeeded; the window was closed immediately.

On 2026-10-03/04 the basic-command build was flashed to the identified COM6
ESP32-H2. A full 4 MB pre-update flash backup is stored outside the repository;
only the application partition at `0x20000` was written, leaving NVS and the
Zigbee network credentials intact. The board announced itself again on the
existing network. This is a firmware/rejoin check, not a fresh IR test.

## Wire protocols v1 and v2

- Endpoint `10`, Home Automation profile `0x0104`, private cluster `0xFF00`.
- Client command `0x00`: six data bytes
  `[version=1, profile=1, command=1, request_id little-endian 24-bit]`.
- Client command `0x02` (v2): eight data bytes
  `[version=2, profile=1, command, temperature, fan, request_id LE24]`.
  Command IDs 1–10 are `POWER_OFF`, `COOL_STATE`, `MODE_AUTO`, `MODE_DRY`,
  `MODE_FAN_ONLY`, `ECONOMY`, `TURBO`, `LED_TOGGLE`, `AIRFLOW_FIX`, and
  `SWING_TOGGLE`. Only `COOL_STATE` accepts temperature 17–30 °C and fan
  0–3 (auto/low/medium/high); all other commands require zero parameters.
  Profile `1` is Carrier CS-A061GS. Invalid lengths, values, zero request ID,
  and manufacturer-specific frames are rejected. V1 is retained for OFF.
- Server result command `0x01`: version, profile, command, request ID and status:
  `0 accepted`, `1 sent`, `2 failed`, `3 duplicate`, `4 busy`.
- `sent` means RMT finished, **not** that the air conditioner switched off.
- Recent request IDs are remembered in RAM (eight-entry window). Reusing an ID
  in that window does not emit IR again. This is not a durable deduplication
  ledger across restart or after the window rolls over. The web bridge sends
  each command once, without automatic retransmission. Toggle effects such as
  LED and swing should therefore be used deliberately.

The ZCL callback validates and queues the request; a single IR worker owns RMT
and sends the completion result. If RMT fails, further transmissions latch off
until reboot. Network credentials are left in NVS; startup never erases NVS.
Fixed frames are copied from the checked-in Carrier profile. Cooling 17–20 °C
frames were measured; 21–30 °C use the profile's inferred Gray-code rule and
remain unverified on the appliance. `LED_TOGGLE` was captured but its physical
effect has not yet been confirmed. No generic “power toggle” is implemented.

## Zigbee2MQTT converter

The local converter source is
`deploy/zigbee/zigbee2mqtt/external_converters/aircon-h2-ir.mjs`. On 2026-10-03
it was installed on the Pi's Zigbee2MQTT 2.14.1 runtime after an explicit
approval and checksum-guarded preview. The private runtime configuration now
has `advanced.enable_external_js: true`; only this reviewed converter file was
installed, with private file and directory permissions. Zigbee2MQTT reported
the converter loaded and the H2 model supported. This is **not** an IR command
or air-conditioner response test.

Example MQTT payload after the converter is installed and the device is
identified as `aircon_h2_ir_01`:

```json
{"ir_request":{"command":"POWER_OFF","request_id":12345}}
```

Publish to `zigbee2mqtt/aircon_h2_ir_01/set`. The converter publishes
`ir_result` on the device topic with the same request ID. A successful MQTT or
Zigbee send is not proof of IR output: require a `sent` result and a physical
appliance check for end-to-end validation.

## Verification status

1. Completed 2026-10-03: one Pi MQTT `POWER_OFF` request (ID `12495794`)
   produced matching `accepted` and `sent` results; the user separately
   confirmed the A/C physically turned off. See
   `../../docs/assets/terminal/360-h2-zigbee-power-off-one-shot.txt`.
2. The basic-command firmware built and passed host protocol/frame checks;
   app-only flash and rejoin succeeded. The v2 converter and web/API were
   deployed with source/runtime SHA-256 checks and service health checks.
3. Physical dashboard tests of cooling, mode, fan, feature, and web OFF
   commands remain pending. Do not infer appliance state from `sent` alone.
