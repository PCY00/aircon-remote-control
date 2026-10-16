"""Exercise provider outcomes without Google credentials or real notification sends."""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "services/central-server"))
from central_server.fcm import FCMSender


def sender(status, details=None, headers=None):
    item = FCMSender.__new__(FCMSender)
    item.credentials = SimpleNamespace(valid=True, token="fixture-oauth")
    item.url = "https://fcm.googleapis.com/v1/projects/test-project/messages:send"
    calls = []

    class HTTP:
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return SimpleNamespace(
                status_code=status,
                headers=headers or {},
                content=b"{}",
                json=lambda: {"error": {"details": details or []}},
            )

    item.http = HTTP()
    return item, calls


def recipient():
    return dict(
        token="fixture-token",
        id="fixture-message",
        binding="fixture-binding",
        subject="fixture-uid",
        kind="event",
        expires_at=time.time() + 250,
        home_id="private-home",
        payload={"private": "sensor"},
    )


@pytest.mark.parametrize(
    "category,alert,level,priority,urgency",
    [
        ("other", "other", "alert", "HIGH", "high"),
        ("climate", "report", "alert", "NORMAL", "high"),
        ("climate", "report", "urgent", "HIGH", "high"),
        ("door", "security", "alert", "HIGH", "high"),
        ("other", "safety", "urgent", "HIGH", "high"),
        ("other", "environment", "quiet", "HIGH", "normal"),  # never queued; header still defined
    ],
)
def test_http_v1_is_data_only_and_contains_no_home_or_sensor_details(
    category, alert, level, priority, urgency
):
    item, calls = sender(200)
    chosen = {"category": category, "alert_category": alert, "level": level}
    assert item.send(recipient() | chosen) == ("accepted", 0)
    url, options = calls[0]
    message = options["json"]["message"]
    assert url == item.url and options["allow_redirects"] is False
    assert set(message) == {"token", "data", "android", "webpush"}
    assert set(message["data"]) == {
        "message_id", "binding", "recipient", "kind", "category", "alert_category", "level"
    }
    assert {key: message["data"][key] for key in chosen} == chosen
    assert all(isinstance(value, str) for value in message["data"].values())
    assert "private-home" not in str(message) and "sensor" not in str(message)
    assert message["android"]["priority"] == priority
    # Web push (iPhone home-screen app) carries the same data plus only Urgency and TTL headers.
    ttl = int(message["android"]["ttl"].removesuffix("s"))
    assert message["webpush"] == {"headers": {"Urgency": urgency, "TTL": str(ttl)}}
    assert 0 < ttl <= 300


@pytest.mark.parametrize(
    "status,expected",
    [(401, "retry"), (429, "retry"), (500, "retry"), (403, "rejected"), (400, "rejected")],
)
def test_provider_rejections_are_classified_without_response_leak(status, expected):
    item, _ = sender(status)
    assert item.send(recipient())[0] == expected


def test_only_explicit_unregistered_disables_a_token_not_generic_bad_request():
    details = [
        {
            "@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError",
            "errorCode": "UNREGISTERED",
        }
    ]
    item, _ = sender(404, details)
    assert item.send(recipient())[0] == "unregistered"
    item, _ = sender(400, [{"errorCode": "INVALID_ARGUMENT"}])
    assert item.send(recipient())[0] == "rejected"


def test_retry_after_bounded_and_expired_message_not_sent():
    item, calls = sender(429, headers={"Retry-After": "99999"})
    assert item.send(recipient()) == ("retry", 300)
    item, calls = sender(200)
    data = recipient()
    data["expires_at"] = time.time() - 1
    assert item.send(data) == ("rejected", 0) and not calls
