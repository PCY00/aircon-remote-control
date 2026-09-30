"""Capture lifecycle orchestration independent of FastAPI and hardware details."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.ir.backend import (
    ReceiverBackend,
    ReceiverError,
    ReceiverTimeoutError,
)
from app.ir.parser import IrParseError
from app.ir.profiles import ProfileRegistry
from app.ir.store import CaptureStore

TERMINAL_STATUSES = {"completed", "timed_out", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class CaptureRecord:
    id: str
    name: str
    profile_id: str
    status: str = "capturing"
    created_at: str = field(default_factory=_now)
    completed_at: str | None = None
    analysis: dict[str, object] | None = None
    error: str | None = None
    files: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "profile_id": self.profile_id,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "analysis": self.analysis,
            "error": self.error,
            "files": self.files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaptureRecord:
        return cls(
            id=data["id"],
            name=data["name"],
            profile_id=data.get("profile_id", "generic"),
            status=data["status"],
            created_at=data["created_at"],
            completed_at=data.get("completed_at"),
            analysis=data.get("analysis"),
            error=data.get("error"),
            files=data.get("files", {}),
        )


class CaptureBusyError(RuntimeError):
    """Raised when a second capture is requested while hardware is busy."""


class CaptureNotFoundError(KeyError):
    """Raised for unknown capture identifiers."""


class CaptureService:
    def __init__(
        self,
        backend: ReceiverBackend,
        store: CaptureStore,
        profiles: ProfileRegistry,
        default_timeout_seconds: float,
    ) -> None:
        self._backend = backend
        self._store = store
        self._profiles = profiles
        self._default_timeout_seconds = default_timeout_seconds
        self._records = {
            item["id"]: CaptureRecord.from_dict(item)
            for item in store.load_all()
            if isinstance(item.get("id"), str)
        }
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._active_id: str | None = None
        self._lock = asyncio.Lock()

    def receiver_status(self) -> dict[str, object]:
        result = self._backend.status().to_dict()
        result["active_capture_id"] = self._active_id
        return result

    def profiles(self) -> list[dict[str, str]]:
        return self._profiles.list()

    def list(self) -> list[dict[str, Any]]:
        records = sorted(self._records.values(), key=lambda item: item.created_at, reverse=True)
        return [record.to_dict() for record in records]

    def get(self, capture_id: str) -> dict[str, Any]:
        try:
            return self._records[capture_id].to_dict()
        except KeyError as exc:
            raise CaptureNotFoundError(capture_id) from exc

    async def start(
        self,
        name: str,
        profile_id: str,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        profile = self._profiles.get(profile_id)
        timeout = timeout_seconds or self._default_timeout_seconds
        async with self._lock:
            if self._active_id is not None:
                raise CaptureBusyError(self._active_id)
            record = CaptureRecord(id=str(uuid4()), name=name, profile_id=profile.profile_id)
            self._records[record.id] = record
            self._active_id = record.id
            task = asyncio.create_task(self._run(record, timeout))
            self._tasks[record.id] = task
        return record.to_dict()

    async def _run(self, record: CaptureRecord, timeout_seconds: float) -> None:
        raw: str | None = None
        try:
            raw = await self._backend.capture_once(timeout_seconds)
            profile = self._profiles.get(record.profile_id)
            record.analysis = profile.analyze(raw)
            record.status = "completed"
        except ReceiverTimeoutError as exc:
            record.status = "timed_out"
            record.error = str(exc)
        except asyncio.CancelledError:
            record.status = "cancelled"
            record.error = "capture was cancelled"
        except (ReceiverError, IrParseError, OSError) as exc:
            record.status = "failed"
            record.error = str(exc)
        finally:
            record.completed_at = _now()
            try:
                record.files = self._store.save(record.id, record.to_dict(), raw)
            except OSError as exc:
                record.status = "failed"
                record.error = f"failed to persist capture: {exc}"
            async with self._lock:
                if self._active_id == record.id:
                    self._active_id = None
                self._tasks.pop(record.id, None)

    async def cancel(self, capture_id: str) -> dict[str, Any]:
        record = self._records.get(capture_id)
        if record is None:
            raise CaptureNotFoundError(capture_id)
        task = self._tasks.get(capture_id)
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        return record.to_dict()

    async def delete(self, capture_id: str) -> None:
        record = self._records.get(capture_id)
        if record is None:
            raise CaptureNotFoundError(capture_id)
        if record.status not in TERMINAL_STATUSES:
            await self.cancel(capture_id)
        self._store.delete(capture_id)
        self._records.pop(capture_id, None)

    async def shutdown(self) -> None:
        active_tasks = [task for task in self._tasks.values() if not task.done()]
        for task in active_tasks:
            task.cancel()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)
