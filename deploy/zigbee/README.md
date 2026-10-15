# Raspberry Pi Zigbee gateway deployment

This directory contains source-controlled templates only. Runtime state and secrets live under
`runtime/zigbee/` on the Raspberry Pi and must never be synchronized back into the repository.

## Components

- `eclipse-mosquitto:2.1.2-alpine`: local MQTT broker
- `ghcr.io/koenkk/zigbee2mqtt:2.14.1`: Zigbee to MQTT bridge
- SONOFF ZBDongle-P: `zstack` Coordinator mapped to `/dev/ttyUSB0` inside the container
- Zigbee channel `20`: selected before pairing any device

Broker identities (`runtime/zigbee/mosquitto/passwords`, hashed) and their topic
permissions (`mosquitto/acl.conf`, source-controlled):

- `zigbee2mqtt`: `readwrite zigbee2mqtt/#` (Zigbee2MQTT itself and the admin scripts)
- `aircon-controller`: `read zigbee2mqtt/#`, `write zigbee2mqtt/+/set`,
  `write zigbee2mqtt/bridge/request/permit_join` (the Pi web app only)

Every other topic is denied once the ACL file is active. The helper scripts never put a
broker password on a command line: `docker exec -e MQTT_PW` propagates it from the
script's environment and the client reads it from a private `$XDG_CONFIG_HOME` options
file inside the container. Password hashes are produced with `mosquitto_passwd -U` on
mode-600 files.

The host publishes MQTT and the Zigbee2MQTT frontend only on loopback:

- MQTT: `127.0.0.1:1883`
- Zigbee2MQTT frontend: `127.0.0.1:8080`

Use an SSH tunnel for the initial administration page:

```powershell
ssh -i "$HOME/.ssh/airconpi" -L 8080:127.0.0.1:8080 air@AC
```

Then open `http://127.0.0.1:8080`. The frontend token is stored only in the Pi runtime secrets
file. Do not copy it into documentation or screenshots.

## Deployment order

1. Run `scripts/deploy_zigbee.ps1` locally to preview the exact files.
2. After approval, run it with `-Apply` to transfer only the Zigbee deployment files.
3. On the Pi, run `sudo scripts/install_zigbee_host.sh` once.
4. Log out and back in so the new `docker` group is applied.
5. Run `scripts/setup_zigbee_stack.sh` as `air`.
6. Run `scripts/setup_app_mqtt.sh` as `air` to create the `aircon-controller` broker user,
   reload Mosquitto (SIGHUP) and point the web app at its own credentials.
7. Run `scripts/check_zigbee_stack.sh` as `air` (verifies the ACL mount and the app user).
8. Create a sensitive local backup with `scripts/backup_zigbee_stack.sh`.

`mosquitto.conf` and `acl.conf` are bind-mounted read-only, so a changed broker
configuration only takes effect after the container is recreated. After deploying a new
`compose.yaml`, `mosquitto.conf` or `acl.conf`, run `scripts/setup_zigbee_stack.sh` again
(its `docker compose up -d` recreates `aircon-mosquitto`; Zigbee2MQTT reconnects on its own)
or run `docker compose --env-file runtime/zigbee/stack.env --file deploy/zigbee/compose.yaml
up -d --force-recreate mosquitto`. Password-file edits by `setup_app_mqtt.sh` only need the
SIGHUP it sends. Note: `scripts/deploy_zigbee.ps1` lists its files explicitly; the full
`scripts/deploy.ps1` run copies `deploy/zigbee/mosquitto/acl.conf` as part of `deploy/`.

The backup command briefly stops both Zigbee2MQTT and Mosquitto so the database, Coordinator
backup, broker persistence, and secrets are copied as one consistent snapshot. It starts both
containers again before returning. Run it during a short maintenance window.

The setup script is idempotent: it creates secrets and mutable Zigbee2MQTT configuration only
when missing. It does not overwrite an existing network.

## Runtime layout on the Pi

```text
runtime/zigbee/
├─ stack.env                         # Compose host paths, mode 600
├─ mosquitto/
│  ├─ passwords                     # hashed MQTT passwords (zigbee2mqtt, aircon-controller), mode 600
│  └─ data/                         # retained broker state
├─ zigbee2mqtt/
│  ├─ configuration.yaml            # mutable runtime configuration
│  ├─ secret.yaml                   # MQTT password, network key, UI token
│  ├─ coordinator_backup.json       # created by Zigbee2MQTT when supported
│  └─ database.db                   # paired device database
└─ backups/                         # sensitive archives, mode 700/600
```

Never publish the contents of `secret.yaml`, `stack.env`, `database.db`, Coordinator backups or
backup archives.

## H2 IR external converter (explicit opt-in)

`deploy/zigbee/zigbee2mqtt/external_converters/aircon-h2-ir.mjs` is the local
source of truth. The converter accepts only the `POWER_OFF` request schema.
Zigbee2MQTT 2.11+ disables external JavaScript by default on new installs,
and enabling it allows arbitrary code from the runtime converter directory.
Keep that directory private, install only reviewed files, and do not enable it
for unrelated devices.

Deploy the reviewed converter and `scripts/install_h2_zigbee_converter.py` from
this checkout to the same relative paths on the Pi. Preview with
`python3 scripts/install_h2_zigbee_converter.py`; pass its `CONFIG_SHA256` to
`--apply --expected-config-sha256 <hash>` only after comparing the Pi files.
The installer keeps the runtime configuration and a private backup on the Pi,
never copies secrets into this repository, and does not restart the gateway.
Restart only `aircon-zigbee2mqtt` in a short maintenance window, then verify
the converter loaded, the H2 is supported, existing sensors remain registered,
and `permit_join=false`. Do not claim IR control until a real command/result
and the air conditioner's response are separately tested.

## Pinned versions and updates

Versions are intentionally pinned in `compose.yaml`. Do not replace them with `latest` during
normal operation. Review release notes, update the local file, take a backup, deploy with approval,
and verify Coordinator and devices after every update.
