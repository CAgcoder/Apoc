"""Generation cancellation registry.

Thread-safe set of project IDs for which cancellation has been requested.
Generation nodes call raise_if_cancelled() at phase boundaries to exit cleanly.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_cancelled: set[str] = set()


class GenerationCancelled(Exception):
    pass


def request_cancel(project_id: str) -> None:
    with _lock:
        _cancelled.add(project_id)


def is_cancelled(project_id: str) -> bool:
    with _lock:
        return project_id in _cancelled


def clear(project_id: str) -> None:
    with _lock:
        _cancelled.discard(project_id)


def raise_if_cancelled(project_id: str) -> None:
    if is_cancelled(project_id):
        raise GenerationCancelled(project_id)
