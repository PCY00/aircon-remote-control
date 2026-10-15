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

The 2026-10-11 restore found a different existing partition table: the actual
factory app began at `0x10000`. After a full private backup and explicit user
confirmation, only that app was replaced. Readback matched the 511,168-byte
build and all flash sectors outside the app write stayed unchanged. The H2
booted and subsequently announced on the existing Pi network; permit-join
was confirmed closed. Always read the installed partition table before an
update; do not copy the older `0x20000` offset blindly. See the
[restore record](../../docs/journal/2026-10-11-h2-firmware-restore.md).
The existing v2 firmware already accepts the commands exposed by family APK
0.5.1. This app update does not require another firmware flash. Physical
responses to all commands have not been tested in this restore.

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
frames were measured; 21–30 °C use the Coolix temperature table
(`0 1 3 2 6 7 5 4 C D 9 8 A B`). It equals Gray code except 27 °C (`0x9`) and
28 °C (`0x8`); the earlier Gray rule sent `0xF`/`0xE` there, and `0xE` is the
fan-only code. 21–30 °C, especially 27/28 °C, remain unverified on the
appliance. `ECONOMY` now sends only the eco/sleep frame `b2 4d e0 1f 03 fc`
(once, as in the capture); the captured press also carried the remote's cool 17 °C/auto state,
which forced 17 °C. The Pi is expected to follow with `COOL_STATE` for the
current setpoint. `LED_TOGGLE` was captured but its physical
effect has not yet been confirmed. No generic “power toggle” is implemented.

If Zigbee initialization/rejoin or network steering fails (for example
`0x03` no network while the Pi coordinator is still starting after a power
cut), the node retries commissioning after 1 s, doubling to at most 60 s,
until it succeeds. A commissioning start the stack refuses is retried the same
way. After a leave without rejoin (for example the device was removed in
Zigbee2MQTT), the node restarts network steering with the same backoff; it
joins again only when the coordinator permits joining. A leave with rejoin is
left to the stack. Retries never emit IR. The RMT TX interrupt is built
cache-safe (`CONFIG_RMT_TX_ISR_CACHE_SAFE=y`) because every command is longer
than the channel memory and Zigbee NVS writes can disable the flash cache.
The build helper regenerates the staging `sdkconfig` whenever
`sdkconfig.defaults` or `partitions.csv` changes.

The private cluster's read-only `capability` attribute (`0x0000`, uint8) is
`2` for this firmware (Coolix 27/28 °C table, eco-only `ECONOMY`, commissioning
retry); the deployed older firmware reports `1`. The converter only declares
the attribute, and the Pi does not read it yet. The Pi backend's new economy
and 27/28 °C behaviour assumes capability 2 firmware, so reflash the H2
together with that Pi deploy. Until then, 27/28 °C stay wrong on the H2 path,
and `ECONOMY` briefly sends the old 17 °C frames before the Pi's `COOL_STATE`.

## Zigbee security

The node trusts the shared Zigbee network key only as far as it has to:

- **Coordinator-only commands.** A private-cluster command is accepted only
  when the ZCL header's source address (`ezb_zcl_cmd_hdr_t.src_addr`) is the
  coordinator's short address `0x0000` in short-address mode; an extended
  source address is first resolved through the stack's address table, and
  group or absent addresses are refused. Zigbee2MQTT on the Pi is the
  coordinator. Any other node, even a joined one holding the network key,
  gets a default response with status `NOT_AUTHORIZED` (`0x7E`) and nothing
  is queued. Rejections are logged on the first occurrence and then at most
  once per minute. The mode is checked strictly because results are addressed
  with this same source address and reached the Pi in the 2026-10-03 test.
  Limitation: the NWK source address is protected only by the shared network
  key, so a device that can forge raw NWK frames as `0x0000` would still pass;
  the pacing below bounds what any sender can do.
- **IR pacing.** The IR worker keeps at least 2 s between the end of one
  transmission and the start of the next appliance-state command
  (`POWER_OFF`, `COOL_STATE`, `MODE_*`, `ECONOMY`) and 0.5 s before a feature
  toggle (`TURBO`, `LED_TOGGLE`, `AIRFLOW_FIX`, `SWING_TOGGLE`). A request is
  still answered `accepted` immediately; only its `sent`/`failed` result
  waits. The Pi sends commands one at a time and waits for `sent`, so in
  normal use only the Pi's `ECONOMY`→`COOL_STATE` follow-up (2 s) and rapid
  repeated clicks are delayed; a full four-deep queue of state commands
  drains in about 7 s, inside the Pi's 18 s result budget. The wire protocol,
  result codes, `capability` (`2`) and the converter are unchanged.
- **Joining.** The node uses the default Trust Center link key and no
  install code (`install_code_policy = false`), so anyone within radio range
  during a permit-join window can obtain the network key. This is an accepted
  risk for the home network: open permit-join only while attending the join,
  keep the window short and close it immediately afterwards. The Pi's
  permit-join request now targets the coordinator only, so routers do not
  re-open the window.

After an approved reflash, verify from the monitor log that the Pi's commands
are still accepted (`from 0x0000 (mode 2)`, or mode `3` resolved through the
address table), that a command from any other node is refused, and that two
back-to-back state commands show a `paced: waiting` line with the second
`sent` result about 2 s later.

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
4. 2026-10-13: the Coolix 27/28 °C table, eco-only `ECONOMY`, commissioning
   retry (including after a leave), capability `2`, and the cache-safe RMT ISR
   were built locally only (`0x7d1d0` bytes, 47% of the app partition free).
   This build has not been flashed. After an approved reflash, check 27/28 °C
   cooling, `ECONOMY` (one eco frame, then the Pi's `COOL_STATE`), and rejoin
   after the Pi coordinator restarts.
5. 2026-10-15: coordinator-only command acceptance and IR pacing (see
   "Zigbee security") were built locally only (`0x7d4a0` bytes, 47% of the
   app partition free) and passed the host policy checks; the wire protocol
   and `capability` are unchanged. Not flashed. After an approved reflash,
   also run the checks listed at the end of "Zigbee security".
