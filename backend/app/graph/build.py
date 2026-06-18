"""Assemble the fusion generation StateGraph.

research -> {candidate_0, candidate_1} (parallel) -> judge -> document
        -> {deck, reviews} (parallel) -> persist
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .. import config
from . import nodes
from .state import PocState


def build_graph():
    g = StateGraph(PocState)
    g.add_node("research", nodes.research_node)

    candidate_names = []
    for index, model in enumerate(config.CANDIDATE_MODELS):
        name = f"candidate_{index}"
        candidate_names.append(name)
        g.add_node(name, nodes.make_candidate_node(index, model))

    g.add_node("judge", nodes.judge_node)
    g.add_node("document", nodes.document_node)
    g.add_node("deck", nodes.deck_node)
    g.add_node("reviews", nodes.reviews_node)
    g.add_node("persist", nodes.persist_node)

    g.add_edge(START, "research")
    for name in candidate_names:
        g.add_edge("research", name)   # fan-out: all candidates after research
        g.add_edge(name, "judge")       # fan-in: judge waits for all candidates
    g.add_edge("judge", "document")
    # fan-out: deck and reviews both depend only on document_md, not on each
    # other, and write disjoint state keys — so run them in parallel.
    g.add_edge("document", "deck")
    g.add_edge("document", "reviews")
    # fan-in: persist waits for both before writing the POC row.
    g.add_edge("deck", "persist")
    g.add_edge("reviews", "persist")
    g.add_edge("persist", END)

    return g.compile(checkpointer=MemorySaver())
