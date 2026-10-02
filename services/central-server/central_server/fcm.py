"""FCM HTTP v1 using Google's auth library and a server-only private credential."""

from __future__ import annotations

import json
import stat
import time
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


class FCMSender:
    def __init__(self, project: str, credential_path: Path):
        if credential_path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise ValueError("Sending credential must be private")
        info = json.loads(credential_path.read_text())
        if (
            info.get("type") != "service_account"
            or info.get("project_id") != project
            or info.get("token_uri") != "https://oauth2.googleapis.com/token"
        ):
            raise ValueError("Sending credential project/type/endpoint mismatch")
        self.credentials = service_account.Credentials.from_service_account_info(
            info, scopes=[SCOPE]
        )
        self.url = "https://fcm.googleapis.com/v1/projects/" + project + "/messages:send"
        self.http = requests.Session()
        self.http.trust_env = False  # server credentials never routed through an inherited proxy

    def send(self, recipient):
        ttl = max(0, min(300, int(recipient["expires_at"] - time.time())))
        if not ttl:
            return "rejected", 0
        message = {
            "token": recipient["token"],
            "data": {
                "message_id": recipient["id"],
                "binding": recipient["binding"],
                "recipient": recipient["subject"],
                "kind": recipient["kind"],
            },
            "android": {"priority": "HIGH", "ttl": str(ttl) + "s"},
        }
        try:
            if not self.credentials.valid:
                auth_request = Request(session=self.http)
                self.credentials.refresh(
                    lambda *args, **kwargs: auth_request(*args, **dict(kwargs, timeout=15))
                )
            response = self.http.post(
                self.url,
                json={"message": message},
                headers={"Authorization": "Bearer " + self.credentials.token},
                timeout=(5, 15),
                allow_redirects=False,
            )
            if response.status_code == 200:
                # Acceptance is not proof the phone displayed the notification.
                return "accepted", 0
            if response.status_code == 401:
                self.credentials.token = None
                return "retry", 30
            if response.status_code == 429 or response.status_code >= 500:
                wait = response.headers.get("Retry-After", "")
                return "retry", min(int(wait), 300) if wait.isdigit() else 60
            if len(response.content) <= 65536:
                try:
                    details = response.json().get("error", {}).get("details", [])
                    if any(
                        item.get("@type") == "type.googleapis.com/google.firebase.fcm.v1.FcmError"
                        and item.get("errorCode") == "UNREGISTERED"
                        for item in details
                    ):
                        return "unregistered", 0
                except (ValueError, AttributeError, TypeError):
                    pass
            return "rejected", 0
        except Exception:
            # OAuth/network errors can contain private payloads: log only a fixed outcome.
            return "retry", 30
