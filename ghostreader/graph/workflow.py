"""LangGraph workflow definition for Ghostreader analysis pipeline.

Graph topology:
    START → [prose + narrative + consistency] → synthesis

Ingestion, fact extraction and repetition detection run before the graph
and fill the initial state. The analyst nodes run in parallel.
The --depth flag controls which analysts run:
    - "quick": prose only (skip narrative + consistency)
    - "standard": prose + narrative + consistency (default)
    - "deep": all three, and the analysts see whole chapters (up to 16k
      chars each) in place of 4k excerpts; costs more tokens
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from ghostreader.agents.consistency_checker import (
    consistency_checker_node,
    scene_consistency_checker_node,
)
from ghostreader.agents.narrative_analyst import narrative_analyst_node
from ghostreader.agents.prose_analyst import prose_analyst_node
from ghostreader.agents.synthesis import synthesis_node
from ghostreader.graph import AnalysisState


# ── Node wrappers that close over the LLM ───────────────────────────
# LangGraph nodes receive only state. We use partial application to
# bind the LLM instance at graph-build time.


def _make_prose_node(llm: BaseChatModel, typesafe_client: Any = None):  # noqa: ANN202
    async def _node(state: AnalysisState) -> dict[str, Any]:
        return await prose_analyst_node(state, llm, typesafe_client=typesafe_client)

    return _node


def _make_narrative_node(llm: BaseChatModel, typesafe_client: Any = None):  # noqa: ANN202
    async def _node(state: AnalysisState) -> dict[str, Any]:
        return await narrative_analyst_node(state, llm, typesafe_client=typesafe_client)

    return _node


def _make_consistency_node(llm: BaseChatModel, typesafe_client: Any = None):  # noqa: ANN202
    async def _node(state: AnalysisState) -> dict[str, Any]:
        return await scene_consistency_checker_node(state, llm, typesafe_client=typesafe_client)

    return _node


def _make_synthesis_node(llm: BaseChatModel):  # noqa: ANN202
    async def _node(state: AnalysisState) -> dict[str, Any]:
        return await synthesis_node(state, llm)

    return _node


# ── Conditional routing ──────────────────────────────────────────────


def _route_after_repetition(
    state: AnalysisState,
) -> list[str]:
    """Determine which analyst nodes to fan out to based on --depth.

    Returns a list of node names for LangGraph's conditional fan-out.
    """
    config = state.get("config", {})
    depth = config.get("depth", "standard")

    if depth == "quick":
        return ["prose_analyst"]

    # "standard" and "deep" run all three analysts
    return ["prose_analyst", "narrative_analyst", "consistency_checker"]


# ── Graph builder ────────────────────────────────────────────────────


def build_analysis_graph(
    llm: BaseChatModel,
    *,
    typesafe_client: Any | None = None,
) -> Any:
    """Build and compile the LangGraph analysis workflow.

    Args:
        llm: The langchain BaseChatModel to use for all agent LLM calls.
        typesafe_client: Optional live AsyncTypeSafeClient closed over by
            analyst nodes. Never stored in AnalysisState.

    Returns:
        A compiled LangGraph that can be invoked with AnalysisState.
    """
    graph = StateGraph(AnalysisState)

    # ── Add nodes ──
    graph.add_node("prose_analyst", _make_prose_node(llm, typesafe_client))
    graph.add_node("narrative_analyst", _make_narrative_node(llm, typesafe_client))
    graph.add_node("consistency_checker", _make_consistency_node(llm, typesafe_client))
    graph.add_node("synthesis", _make_synthesis_node(llm))

    # ── Define edges ──
    # Fan-out by depth: START → [prose, narrative, consistency]
    graph.add_conditional_edges(
        START,
        _route_after_repetition,
        {
            "prose_analyst": "prose_analyst",
            "narrative_analyst": "narrative_analyst",
            "consistency_checker": "consistency_checker",
        },
    )

    # All analysts converge to synthesis
    graph.add_edge("prose_analyst", "synthesis")
    graph.add_edge("narrative_analyst", "synthesis")
    graph.add_edge("consistency_checker", "synthesis")

    # Synthesis → END
    graph.add_edge("synthesis", END)

    return graph.compile()


__all__ = ["build_analysis_graph"]
