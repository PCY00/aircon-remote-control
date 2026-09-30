"""Atomic persistence for learned IR captures."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from app.ir.parser import normalize_compact, to_irctl_send_text


class CaptureStore:
    """Keep metadata and replay-ready raw data under the runtime directory."""

    def __init__(self, data_dir: Path) -> None:
        self._directory = data_dir / "captures"

    @property
    def directory(self) -> Path:
        return self._directory

    def _atomic_write(self, destination: Path, content: str) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", dir=destination.parent, text=True
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

    def save(self, capture_id: str, metadata: dict[str, object], raw: str | None) -> dict[str, str]:
        files = {"metadata": f"{capture_id}.json"}
        if raw is not None:
            files.update(
                {
                    "compact": f"{capture_id}.compact",
                    "irctl": f"{capture_id}.ir",
                }
            )
            self._atomic_write(self._directory / files["compact"], normalize_compact(raw))
            self._atomic_write(self._directory / files["irctl"], to_irctl_send_text(raw))

        stored_metadata = dict(metadata)
        stored_metadata["files"] = files
        self._atomic_write(
            self._directory / files["metadata"],
            json.dumps(stored_metadata, ensure_ascii=False, indent=2) + "\n",
        )
        return files

    def load_all(self) -> list[dict[str, object]]:
        if not self._directory.exists():
            return []
        captures: list[dict[str, object]] = []
        for path in self._directory.glob("*.json"):
            try:
                captures.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return captures

    def delete(self, capture_id: str) -> bool:
        deleted = False
        for suffix in (".json", ".compact", ".ir"):
            path = self._directory / f"{capture_id}{suffix}"
            if path.exists():
                path.unlink()
                deleted = True
        return deleted
