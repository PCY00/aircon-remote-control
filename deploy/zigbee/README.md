# Raspberry Pi Zigbee gateway deployment

This directory contains source-controlled templates only. Runtime state and secrets live under
`runtime/zigbee/` on the Raspberry Pi and must never be synchronized back into the repository.

## Components

- `eclipse-mosquitto:2.1.2-alpine`: local MQTT broker
- `ghcr.io/koenkk/zigbee2mqtt:2.14.1`: Zigbee to MQTT bridge
- SONOFF ZBDongle-P: `zstack` Coordinator mapped to `/dev/ttyUSB0` inside the container
- Zigbee channel `20`: selected before pairing any device

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
6. Run `scripts/check_zigbee_stack.sh` as `air`.
7. Create a sensitive local backup with `scripts/backup_zigbee_stack.sh`.

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
│  ├─ passwords                     # hashed MQTT password, mode 600
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

## Pinned versions and updates

Versions are intentionally pinned in `compose.yaml`. Do not replace them with `latest` during
normal operation. Review release notes, update the local file, take a backup, deploy with approval,
and verify Coordinator and devices after every update.
