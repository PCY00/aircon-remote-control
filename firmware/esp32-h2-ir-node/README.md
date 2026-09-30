# ESP32-H2 SuperMini IR node firmware

This is the first Step 4 bring-up firmware. It verifies the USB-powered
ESP32-H2 SuperMini, GPIO8, AO3400A and one 940 nm IR LED before adding Zigbee.

The firmware starts idle. It never sends an air-conditioner command only because
the board booted.

## Console commands

- `c`: send ten short 38 kHz carrier bursts for a phone-camera test
- `5`: run a five-second camera test (25 bursts; no A/C command)
- `n`: send Carrier CS-A061GS `POWER_ON_COOL_17_HIGH`
- `f`: send Carrier CS-A061GS `POWER_OFF`
- `h`: print help

## Build and flash

The project source remains in this repository. Because ESP-IDF on Windows does
not reliably support non-ASCII paths, `scripts/esp32_h2_firmware.ps1` copies only
the firmware sources into the ASCII-only staging directory
`C:\esp\aircon-h2-ir-node-<checkout-hash>` and keeps generated build files there. Always
edit the repository source, not the staging copy.

```powershell
./scripts/esp32_h2_firmware.ps1 build
./scripts/esp32_h2_firmware.ps1 flash -Port COMx
./scripts/esp32_h2_firmware.ps1 monitor -Port COMx
```

Discover the actual serial port on each computer instead of assuming that the
port used on a previous computer is still correct. `flash` and `monitor` require
an explicit `-Port`; the helper never defaults to a previously connected device.
The script prints `BUILD_DIRECTORY` so that the resulting `build/` binaries can
be found. Separate checkouts get separate staging directories.

Use `-IdfPath` for the SDK location, `-IdfToolsPath` for the installed toolchain
directory, and `-BuildRoot` for a writable ASCII staging root if necessary. An
existing `IDF_TOOLS_PATH` is respected; otherwise tools default to `C:\Espressif`.
The old `C:\esp\aircon-h2-ir-node-build` is retained but no longer updated.

## Validation status and fault handling

The 2026-09-12 source improvements have not been flashed to the physical board.
Do not infer the installed firmware version from the staging files alone.

GPIO8 is the physically confirmed pin. Camera-visible IR emission was observed;
carrier frequency and pulse timings have not been measured on the output.
Carrier A/C `POWER_OFF` has not yet succeeded on this H2 setup. A transmission
completion log only means the RMT driver finished processing its buffer.

Carrier packet data is isolated in `main/carrier_profile.h`. Host regression
tests compare the actual C encoder output with the Raspberry Pi command profile.
They do not verify physical carrier frequency, power, or A/C reception.

The current console processes one command at a time. Wait for completion before
sending another command; use `5` for a longer camera test instead of queuing `ccc`.
A TX error latches a fault and rejects further transmissions until reset. Its
static payload remains valid even if the RMT driver cannot finish or stop.

This project's current SDK is ESP-IDF 5.5.4. Zigbee integration will be added only
after standalone RMT transmission succeeds.

Run host checks with `python -m pytest tests/test_h2_ir_firmware.py`. They require
a host GCC or Clang compiler (on this PC: `C:\msys64\ucrt64\bin\gcc.exe`) and skip when one
is unavailable; a skipped host check is not a successful hardware test.
