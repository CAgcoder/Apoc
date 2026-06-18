"""Typed state for the fusion generation graph.

`candidates` is written by two parallel nodes, so it uses an append reducer —
without it, concurrent writes to the same key raise an InvalidUpdateError in
LangGraph.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict


def merge_candidates(
    left: list[dict[str, Any]] | None, right: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    return (left or []) + (right or [])


class PocState(TypedDict, total=False):
    project_id: str
    run_id: str
    brief_text: str
    title: str
    client_name: str
    consulting_org: str
    # research
    digest: str
    sources: list[dict[str, Any]]
    # fan-out: each candidate node appends one {"id","model","design"} dict
    candidates: Annotated[list[dict[str, Any]], merge_candidates]
    # judge
    canonical: dict[str, Any]
    guidance: dict[str, Any]
    manifest: list[dict[str, Any]]
    # document
    document_md: str
    # deck
    deck_html: str
    deck_css: str
    # reviews
    reviews: list[dict[str, Any]]
    annotations: list[dict[str, Any]]
    # persistence
    poc_id: str
