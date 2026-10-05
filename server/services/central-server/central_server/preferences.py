"""Phone-specific notification consent and interval selection, separate from family authority."""

DEFAULTS = {"door": True, "climate": False, "warning": True, "climate_interval_minutes": 5}
STATEMENTS = (
    "ALTER TABLE homes ADD COLUMN active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))",
    """CREATE TABLE notification_preferences (
        installation_id TEXT PRIMARY KEY REFERENCES installations(id),
        user_id TEXT NOT NULL REFERENCES users(id),
        door INTEGER NOT NULL DEFAULT 1 CHECK(door IN (0,1)),
        climate INTEGER NOT NULL DEFAULT 0 CHECK(climate IN (0,1)),
        warning INTEGER NOT NULL DEFAULT 1 CHECK(warning IN (0,1)),
        climate_interval_minutes INTEGER NOT NULL DEFAULT 5
            CHECK(climate_interval_minutes IN (1,5,15,60)),
        last_climate_at REAL NOT NULL DEFAULT 0)""",
)


def category(kind):
    if kind in ("sensor.door_changed", "sensor.open", "sensor.closed"):
        return "door"
    if kind == "sensor.climate_report":
        return "climate"
    if kind in ("automation.warning_triggered", "automation.warning_resolved"):
        return "warning"
    return "other"


def read(conn, installation, user):
    row = conn.execute(
        "SELECT * FROM notification_preferences WHERE installation_id=? AND user_id=?",
        (installation, user),
    ).fetchone()
    return (
        {key: bool(row[key]) if key != "climate_interval_minutes" else row[key] for key in DEFAULTS}
        if row
        else dict(DEFAULTS)
    )


def permits(conn, installation, user, selected):
    return selected == "other" or read(conn, installation, user)[selected]
