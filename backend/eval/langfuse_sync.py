"""Host the eval in Langfuse — two paths that coexist:

1. ``push_scores`` — our own objective counts (eval.metrics) pushed as Langfuse
   scores. Langfuse stores/visualizes; the scoring logic stays in Python because
   no built-in metric expresses "trade-off count".
2. ``push_coverage_dataset`` — uploads each (requirement, design-mapping) pair as
   a Langfuse dataset item so a **Langfuse-native LLM-as-judge evaluator**
   (configured in the UI) can score requirement coverage. This is the one piece
   of the eval that is genuinely a rubric judgment, so it gets the native path.

Score values must be numbers (booleans cast to 0/1).
"""

from __future__ import annotations

from typing import Any

from . import coverage


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return None  # non-numeric skipped


def push_scores(
    client: Any, *, dataset_run: str, brief_slug: str,
    per_contestant: dict[str, dict[str, Any]],
) -> None:
    """Emit one Langfuse score per (contestant, numeric metric)."""
    for contestant, scores in per_contestant.items():
        for name, value in scores.items():
            num = _numeric(value)
            if num is None:
                continue
            client.create_score(
                name=name,
                value=num,
                metadata={"contestant": contestant, "brief": brief_slug, "run": dataset_run},
            )


def push_coverage_dataset(
    client: Any, *, dataset_name: str, brief_slug: str, contestant: str,
    design: dict[str, Any], checklist: list[str],
) -> None:
    """Upload one dataset item per checklist requirement for native evaluation.

    Each item: input = the frozen requirement, expected_output = the design's
    requirements-mapping text. A Langfuse LLM-as-judge evaluator (configured in
    the UI to read {{input}} / {{expected_output}}) then scores "addressed".
    """
    client.create_dataset(name=dataset_name)
    mapping_text = coverage._mapping_text(design)
    for requirement in checklist:
        client.create_dataset_item(
            dataset_name=dataset_name,
            input=requirement,
            expected_output=mapping_text,
            metadata={"contestant": contestant, "brief": brief_slug},
        )


def get_client():  # pragma: no cover - thin SDK wrapper
    from langfuse import Langfuse

    return Langfuse()
