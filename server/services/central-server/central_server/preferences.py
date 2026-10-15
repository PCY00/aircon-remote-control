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

# Schema 7: one importance level per alert category and phone. Only urgent and alert reach the
# phone; quiet and off stay in the home's history. 'other' is not configurable and always sent.
LEVELS = ("urgent", "alert", "quiet", "off")
PUSHED = ("urgent", "alert")
CATEGORIES = {"safety": "urgent", "security": "alert", "device": "alert", "environment": "quiet",
              "report": "off", "automation": "alert", "family": "quiet"}  # name: default level
CHOICES = {name: PUSHED if name == "safety" else LEVELS for name in CATEGORIES}
INTERVALS = (1, 5, 15, 60)
LEGACY = {"door": "security", "climate": "report", "warning": "automation"}  # old switch: category
LEVEL_STATEMENTS = (
    """CREATE TABLE notification_levels (
        installation_id TEXT NOT NULL REFERENCES installations(id),
        user_id TEXT NOT NULL REFERENCES users(id), category TEXT NOT NULL,
        level TEXT NOT NULL CHECK(level IN ('urgent','alert','quiet','off')),
        PRIMARY KEY(installation_id,category))""",
    # Each phone's saved switches carry over with the same meaning: on -> alert, off -> off.
    *(f"""INSERT INTO notification_levels(installation_id,user_id,category,level)
          SELECT p.installation_id,p.user_id,'{new}',CASE WHEN p.{old}=1 THEN 'alert' ELSE 'off' END
          FROM notification_preferences p JOIN installations i ON i.id=p.installation_id
          JOIN users u ON u.id=p.user_id"""
      for old, new in LEGACY.items()),
)


def category(kind):
    """Legacy FCM category: old app builds drop values they do not know."""
    if kind in ("sensor.door_changed", "sensor.open", "sensor.closed"):
        return "door"
    if kind == "sensor.climate_report":
        return "climate"
    if kind in ("automation.warning_triggered", "automation.warning_resolved"):
        return "warning"
    return "other"


def alert_category(kind):
    """Alert category of an event kind; tests and unknown kinds are 'other'."""
    kind = kind or ""
    if kind.startswith("safety.") or kind in ("sensor.leak_detected", "sensor.smoke_detected"):
        return "safety"
    if kind in ("sensor.door_changed", "sensor.open", "sensor.closed", "sensor.motion_detected"):
        return "security"
    if kind.startswith("device."):
        return "device"
    if kind.startswith("environment.") or kind == "sensor.climate_threshold":
        return "environment"
    if kind == "sensor.climate_report":
        return "report"
    if kind.startswith("automation."):
        return "automation"
    if kind.startswith("family."):
        return "family"
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


def levels(conn, installation, user):
    """Saved level per category for this account, else the default; others' rows never count."""
    saved = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT category,level FROM notification_levels WHERE installation_id=? AND user_id=?",
            (installation, user),
        )
    }
    return {name: saved.get(name, default) for name, default in CATEGORIES.items()}


def level(conn, installation, user, selected):
    return "alert" if selected == "other" else levels(conn, installation, user)[selected]
