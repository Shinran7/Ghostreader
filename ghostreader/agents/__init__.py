"""Analysis agents — LangGraph node functions for literary analysis."""

from ghostreader.agents.consistency_checker import consistency_checker_node
from ghostreader.agents.genre_prompts import get_genre_preamble
from ghostreader.agents.narrative_analyst import narrative_analyst_node
from ghostreader.agents.prose_analyst import prose_analyst_node
from ghostreader.agents.synthesis import synthesis_node

__all__ = [
    "consistency_checker_node",
    "get_genre_preamble",
    "narrative_analyst_node",
    "prose_analyst_node",
    "synthesis_node",
]
