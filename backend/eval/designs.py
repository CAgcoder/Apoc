"""Load the four ablation contestants from a single run directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONTESTANTS = ["candidate_A", "candidate_B", "opus_solo", "canonical"]
_REQUIRED = ["candidate_A", "candidate_B", "canonical"]


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_contestants(run_dir: Path | str) -> dict[str, dict[str, Any]]:
    """Return {name: design dict}. Required files must exist; opus_solo is optional."""
    run_dir = Path(run_dir)
    out: dict[str, dict[str, Any]] = {}
    for name in _REQUIRED:
        path = run_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"missing required contestant: {path}")
        out[name] = _read(path)
    opus = run_dir / "opus_solo.json"
    if opus.exists():
        out["opus_solo"] = _read(opus)
    return out
