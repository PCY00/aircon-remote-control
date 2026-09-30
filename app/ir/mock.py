"""Deterministic receiver backend for development and automated tests."""

from __future__ import annotations

import asyncio

from app.ir.backend import ReceiverStatus, ReceiverTimeoutError


class MockReceiver:
    """Return queued captures while preserving the production backend contract."""

    def __init__(self, captures: list[str] | None = None, *, wait_forever: bool = False) -> None:
        self._captures = list(captures or [])
        self._wait_forever = wait_forever

    def status(self) -> ReceiverStatus:
        return ReceiverStatus(
            backend="mock",
            available=True,
            command=None,
            device="mock://receiver",
            details="ready",
        )

    async def capture_once(self, timeout_seconds: float) -> str:
        if self._wait_forever:
            await asyncio.Event().wait()
        if not self._captures:
            raise ReceiverTimeoutError(
                f"mock has no packet available within {timeout_seconds:g} seconds"
            )
        await asyncio.sleep(0)
        return self._captures.pop(0)
