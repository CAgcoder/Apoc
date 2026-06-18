"""In-memory progress bus for streaming generation status to the UI.

Generation runs in a background thread (the Anthropic SDK call is synchronous);
the SSE endpoint polls these per-project event lists. Good enough for a
single-process demo — no external broker needed.
"""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_events: dict[str, list[dict[str, Any]]] = {}


def publish(project_id: str, phase: str, **detail: Any) -> None:
    with _lock:
        _events.setdefault(project_id, []).append({"phase": phase, **detail})


def since(project_id: str, cursor: int) -> tuple[list[dict[str, Any]], int]:
    with _lock:
        events = _events.get(project_id, [])
        return events[cursor:], len(events)


def reset(project_id: str) -> None:
    with _lock:
        _events[project_id] = []
