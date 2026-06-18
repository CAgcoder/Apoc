"""Generate the opus-4.8-solo ablation contestant for an existing run.

Reuses the run's persisted research digest so the only difference between this
design and the fused canonical is the fusion step — not grounding or schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app import config, llm, prompts


def generate(run_dir: Path | str, *, brief_text: str, model: str | None = None) -> dict[str, Any]:
    run_dir = Path(run_dir)
    model = model or config.OPUS_SOLO_MODEL
    digest_path = run_dir / "research.raw.txt"
    if not digest_path.exists():
        raise FileNotFoundError(f"no research digest for run: {digest_path}")
    digest = digest_path.read_text(encoding="utf-8")

    user = f"{brief_text}\n\n--- Research digest ---\n{digest}"
    raw_text, _ = llm.run_text(
        system=prompts.candidate_system_for_model(model), user=user, model=model,
        max_tokens=16000, json_mode=True,
    )
    design = llm.extract_json(raw_text)
    if not isinstance(design, dict):
        design = {}
    (run_dir / "opus_solo.json").write_text(
        json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return design
