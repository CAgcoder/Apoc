"""Per-run artifact store: the backbone of progressive disclosure.

Each generation run gets a directory under ``RUNS_DIR``. Candidate designs, the
canonical design, the guidance package, and the 10 fixed document sections are
written here as files. The Haiku document writer never touches the filesystem —
it calls ``read_section`` through a controller-mediated tool, and the store
enforces a path jail so the model can only read sections inside this run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Maps a canonical-design JSON field to a stable section key. Keys mirror the
# canonical design shape produced by the judge.
_SECTION_FIELDS = [
    "title", "executive_summary", "context", "requirements_mapping", "components",
    "data_flows", "tech_stack", "nfrs", "decisions", "risks", "cost_estimate",
    "open_questions",
]


def _render_field(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


class ArtifactStore:
    def __init__(self, runs_dir: Path | str, run_id: str) -> None:
        self.run_id = run_id
        self.dir = Path(runs_dir) / run_id
        self.sections_dir = self.dir / "sections"
        self.sections_dir.mkdir(parents=True, exist_ok=True)

    # --- writing ---------------------------------------------------------
    def write_section(self, key: str, text: str) -> None:
        (self.sections_dir / f"{self._safe(key)}.md").write_text(text, encoding="utf-8")

    def write_text(self, name: str, text: str) -> None:
        (self.dir / f"{self._safe(name)}.txt").write_text(text, encoding="utf-8")

    def write_json(self, name: str, obj: Any) -> None:
        (self.dir / f"{self._safe(name)}.json").write_text(
            json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # --- reading (controller side of the read tool) ----------------------
    def read_section(self, key: str) -> str:
        safe = self._safe(key)
        path = (self.sections_dir / f"{safe}.md").resolve()
        # Path jail: the resolved file must stay inside sections_dir.
        if self.sections_dir.resolve() not in path.parents or not path.exists():
            return f"(no such section: {key})"
        return path.read_text(encoding="utf-8")

    # --- manifest --------------------------------------------------------
    def build_manifest(
        self, canonical: dict[str, Any], summaries: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """Split the canonical design into section files and return a manifest.

        Deterministic — no model call. Each entry: section key, char count, and a
        short summary (caller-provided or truncated).
        """
        summaries = summaries or {}
        manifest: list[dict[str, Any]] = []
        for field in _SECTION_FIELDS:
            if field not in canonical:
                continue
            text = _render_field(canonical[field])
            self.write_section(field, text)
            manifest.append({
                "section": field,
                "chars": len(text),
                "summary": summaries.get(field) or (text[:160].replace("\n", " ")),
            })
        self.write_json("manifest", manifest)
        return manifest

    @staticmethod
    def _safe(key: str) -> str:
        # Strip anything that could escape the run dir; keys are simple slugs.
        safe = "".join(c for c in str(key) if c.isalnum() or c in ("_", "-", ".")).strip(".")
        return safe or "_"
