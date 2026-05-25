"""LangGraph workflow definition for Ghostreader analysis pipeline.

Graph topology:
    ingestion_node → repetition_node → [prose + narrative + consistency] → synthesis

The three analyst nodes run in parallel after repetition detection.
The --depth flag controls which analysts run:
    - "quick": prose only (skip narrative + consistency)
    - "standard": prose + narrative + consistency (default)
    - "deep": same as standard (extensible for future deep-dive agents)
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, StateGraph

from ghostreader.agents.consistency_checker import consistency_checker_node
from ghostreader.agents.narrative_analyst import narrative_analyst_node
from ghostreader.agents.prose_analyst import prose_analyst_node
from ghostreader.agents.synthesis import synthesis_node
from ghostreader.graph import AnalysisState


# ── Stub nodes for ingestion and repetition ─────────────────────────
# These are pass-through stubs. The real ingestion and repetition
# detection run *before* the graph is invoked and populate state
# externally. The nodes exist so the graph topology is explicit and
# can be extended later to run ingestion/repetition inside the graph.


async def ingestion_node(state: AnalysisState) -> dict[str, Any]:
    """Pass-through: ingestion data is pre-loaded into initial state."""
    return {}


async def repetition_node(state: AnalysisState) -> dict[str, Any]:
    """Pass-through: repetition data is pre-computed and loaded into state."""
    return {}


# ── Node wrappers that close over the LLM ───────────────────────────
# LangGraph nodes receive only state. We use partial application to
# bind the LLM instance at graph-build time.


def _make_prose_node(llm: BaseChatModel):  # noqa: ANN202
    async def _node(state: AnalysisState) -> dict[str, Any]:
        return await prose_analyst_node(state, llm)
    return _node


def _make_narrative_node(llm: BaseChatModel):  # noqa: ANN202
    async def _node(state: AnalysisState) -> dict[str, Any]:
        return await narrative_analyst_node(state, llm)
    return _node


def _make_consistency_node(llm: BaseChatModel):  # noqa: ANN202
    async def _node(state: AnalysisState) -> dict[str, Any]:
        return await consistency_checker_node(state, llm)
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


def _route_to_synthesis(state: AnalysisState) -> str:
    """Always route to synthesis after analysts complete."""
    return "synthesis"


# ── Graph builder ────────────────────────────────────────────────────


def build_analysis_graph(llm: BaseChatModel) -> Any:
    """Build and compile the LangGraph analysis workflow.

    Args:
        llm: The langchain BaseChatModel to use for all agent LLM calls.

    Returns:
        A compiled LangGraph that can be invoked with AnalysisState.
    """
    graph = StateGraph(AnalysisState)

    # ── Add nodes ──
    graph.add_node("ingestion", ingestion_node)
    graph.add_node("repetition", repetition_node)
    graph.add_node("prose_analyst", _make_prose_node(llm))
    graph.add_node("narrative_analyst", _make_narrative_node(llm))
    graph.add_node("consistency_checker", _make_consistency_node(llm))
    graph.add_node("synthesis", _make_synthesis_node(llm))

    # ── Define edges ──
    # Linear: ingestion → repetition
    graph.set_entry_point("ingestion")
    graph.add_edge("ingestion", "repetition")

    # Conditional fan-out: repetition → [prose, narrative, consistency]
    graph.add_conditional_edges(
        "repetition",
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
