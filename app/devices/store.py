"""Persistent runtime storage for registered devices and model requests."""

from __future__ import annotations

import json
import os
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class DeviceNotFoundError(LookupError):
    """Raised when a registered device does not exist."""


class InvalidUploadError(ValueError):
    """Raised when a model request contains an unsupported or oversized file."""


@dataclass(frozen=True)
class UploadPayload:
    """A validated-in-memory upload passed from the HTTP layer."""

    filename: str
    content_type: str | None
    data: bytes


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    _atomic_write(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


def _safe_component(value: str, field: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized or len(normalized) > 100:
        raise ValueError(f"{field} must be between 1 and 100 characters")
    safe = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in normalized
    ).strip("._")
    if not safe or safe in {".", ".."}:
        raise ValueError(f"{field} cannot be used as a directory name")
    return safe


class RegisteredDeviceStore:
    """Store each registered appliance independently for safe incremental updates."""

    def __init__(self, data_dir: Path) -> None:
        self._directory = data_dir / "devices"

    def create(
        self,
        name: str,
        room: str,
        profile_id: str,
        icon: str = "box",
    ) -> dict[str, object]:
        device_id = uuid4().hex
        record: dict[str, object] = {
            "id": device_id,
            "name": name,
            "room": room,
            "profile_id": profile_id,
            "icon": icon,
            "created_at": _timestamp(),
            "last_desired_state": None,
            "last_command": None,
        }
        _write_json(self._directory / f"{device_id}.json", record)
        return record

    def list(self) -> list[dict[str, object]]:
        if not self._directory.exists():
            return []
        items: list[dict[str, object]] = []
        for path in self._directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                items.append(payload)
        return sorted(items, key=lambda item: str(item.get("created_at", "")))

    def get(self, device_id: str) -> dict[str, object]:
        if not device_id.isalnum():
            raise DeviceNotFoundError(device_id)
        path = self._directory / f"{device_id}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise DeviceNotFoundError(device_id) from exc
        if not isinstance(payload, dict):
            raise DeviceNotFoundError(device_id)
        return payload

    def record_command(
        self,
        device_id: str,
        *,
        command_id: str,
        command_kind: str,
        effective_state: dict[str, object] | None,
    ) -> dict[str, object]:
        record = self.get(device_id)
        timestamp = _timestamp()
        if effective_state is not None:
            record["last_desired_state"] = {
                **effective_state,
                "confirmation": "inferred_from_ir_command",
            }
        record["last_command"] = {
            "command_id": command_id,
            "kind": command_kind,
            "recorded_at": timestamp,
        }
        record["updated_at"] = timestamp
        _write_json(self._directory / f"{device_id}.json", record)
        return record


class DeviceRequestStore:
    """Keep user uploads outside source-controlled deployment paths."""

    _IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

    def __init__(self, data_dir: Path, max_upload_bytes: int) -> None:
        self._root = data_dir / "device_requests"
        self._max_upload_bytes = max_upload_bytes

    def _validate_file(
        self, upload: UploadPayload, *, kind: str, extensions: set[str]
    ) -> str:
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in extensions:
            allowed = ", ".join(sorted(extensions))
            raise InvalidUploadError(f"{kind} must use one of: {allowed}")
        if not upload.data:
            raise InvalidUploadError(f"{kind} is empty")
        if len(upload.data) > self._max_upload_bytes:
            raise InvalidUploadError(
                f"{kind} exceeds the {self._max_upload_bytes}-byte upload limit"
            )
        if suffix in self._IMAGE_EXTENSIONS and not self._has_image_signature(
            suffix, upload.data
        ):
            raise InvalidUploadError(f"{kind} content does not match {suffix}")
        if suffix == ".pdf" and not upload.data.startswith(b"%PDF-"):
            raise InvalidUploadError("manual content is not a PDF")
        return suffix

    @staticmethod
    def _has_image_signature(suffix: str, data: bytes) -> bool:
        if suffix in {".jpg", ".jpeg"}:
            return data.startswith(b"\xff\xd8\xff")
        if suffix == ".png":
            return data.startswith(b"\x89PNG\r\n\x1a\n")
        if suffix == ".webp":
            return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
        return False

    def create(
        self,
        *,
        device_type: str,
        brand: str,
        model: str,
        product_photo: UploadPayload,
        remote_photo: UploadPayload | None,
        manual: UploadPayload | None,
    ) -> dict[str, object]:
        request_id = uuid4().hex
        directory = self._root.joinpath(
            _safe_component(device_type, "device_type"),
            _safe_component(brand, "brand"),
            _safe_component(model, "model"),
        )
        product_suffix = self._validate_file(
            product_photo, kind="product_photo", extensions=self._IMAGE_EXTENSIONS
        )
        remote_suffix = (
            self._validate_file(
                remote_photo, kind="remote_photo", extensions=self._IMAGE_EXTENSIONS
            )
            if remote_photo is not None
            else None
        )
        manual_suffix = (
            self._validate_file(manual, kind="manual", extensions={".pdf"})
            if manual is not None
            else None
        )

        files: dict[str, str] = {}
        product_path = directory / "photos" / f"product-{request_id}{product_suffix}"
        _atomic_write(product_path, product_photo.data)
        files["product_photo"] = product_path.relative_to(self._root).as_posix()

        if remote_photo is not None:
            assert remote_suffix is not None
            remote_path = directory / "photos" / f"remote-{request_id}{remote_suffix}"
            _atomic_write(remote_path, remote_photo.data)
            files["remote_photo"] = remote_path.relative_to(self._root).as_posix()

        if manual is not None:
            assert manual_suffix is not None
            manual_path = directory / "manuals" / f"manual-{request_id}{manual_suffix}"
            _atomic_write(manual_path, manual.data)
            files["manual"] = manual_path.relative_to(self._root).as_posix()

        metadata: dict[str, object] = {
            "id": request_id,
            "status": "analysis_pending",
            "device_type": device_type.strip(),
            "brand": brand.strip(),
            "model": model.strip(),
            "submitted_at": _timestamp(),
            "files": files,
        }
        _write_json(directory / "requests" / f"{request_id}.json", metadata)
        return metadata
