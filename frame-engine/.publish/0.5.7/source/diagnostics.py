from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol
import json
import threading

from .contract import DiagnosticEvent


class DiagnosticsCollector(Protocol):
    def record(self, event: DiagnosticEvent) -> None: ...


class ListDiagnosticsCollector:
    def __init__(self) -> None:
        self.events: list[DiagnosticEvent] = []

    def record(self, event: DiagnosticEvent) -> None:
        self.events.append(event)


class JsonlDiagnosticsCollector:
    """Append explainable 0.5 decisions beside the existing processing trace.

    The collector deliberately keeps per-event open/close semantics so a trace is
    visible immediately and survives a later analyzer failure. Directory creation
    is cached instead of repeated for every event; if the directory is removed
    while BMB is running, the first failed append recreates it and retries once.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._parent_ready = False

    def _ensure_parent(self) -> None:
        if self._parent_ready:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._parent_ready = True

    def _append_line(self, encoded: str) -> None:
        self._ensure_parent()
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(encoded + "\n")
        except FileNotFoundError:
            # A log cleaner may remove the directory between events. Preserve
            # the previous self-healing behaviour without paying mkdir/stat on
            # every normal record.
            self._parent_ready = False
            self._ensure_parent()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(encoded + "\n")

    def record(self, event: DiagnosticEvent) -> None:
        details = event.details if isinstance(event.details, dict) else dict(event.details)
        payload = {
            "stage": event.stage,
            "code": event.code,
            "message": event.message,
            "frame_key": event.frame_key,
            "details": details,
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._append_line(encoded)


class FanoutDiagnosticsCollector:
    def __init__(self, *collectors: DiagnosticsCollector) -> None:
        self.collectors = tuple(collectors)

    def record(self, event: DiagnosticEvent) -> None:
        for collector in self.collectors:
            try:
                collector.record(event)
            except Exception:
                continue


def emit(
    collector: DiagnosticsCollector | None,
    stage: str,
    code: str,
    message: str,
    *,
    frame_key: str | None = None,
    details: Mapping[str, object] | None = None,
) -> None:
    if collector is None:
        return
    try:
        collector.record(
            DiagnosticEvent(
                stage=stage,
                code=code,
                message=message,
                frame_key=frame_key,
                details=dict(details or {}),
            )
        )
    except Exception:
        return


__all__ = [
    "DiagnosticsCollector",
    "FanoutDiagnosticsCollector",
    "JsonlDiagnosticsCollector",
    "ListDiagnosticsCollector",
    "emit",
]
