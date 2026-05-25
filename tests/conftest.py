"""Shared fixtures for Ghostreader tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from ghostreader.ingestion import Chapter


# ── Sample chapters ──────────────────────────────────────────────────


@pytest.fixture()
def sample_chapters() -> list[Chapter]:
    """Three minimal chapters for unit testing."""
    return [
        Chapter(
            title="The Beginning",
            content=(
                "The old man sat on the porch. He looked at the sky. "
                "The sky was dark and stormy. He sighed deeply.\n\n"
                '"It\'s going to rain," he said quietly.\n\n'
                "The wind picked up and the trees swayed. He stood and "
                "walked inside. The door creaked behind him."
            ),
            chapter_number=1,
            source_path=Path("/fake/chapter-001.md"),
        ),
        Chapter(
            title="The Journey",
            content=(
                "She walked along the river. The river was wide and cold. "
                "She shivered as the wind blew. The trees along the bank "
                "were bare.\n\n"
                '"Where are we going?" she asked nervously.\n'
                '"North," he replied firmly.\n\n'
                "They walked for hours through the forest. The path was "
                "narrow and winding. She stumbled on a root but caught "
                "herself. He didn't notice."
            ),
            chapter_number=2,
            source_path=Path("/fake/chapter-002.md"),
        ),
        Chapter(
            title="The Arrival",
            content=(
                "The town appeared at dawn. Smoke rose from chimneys. "
                "People moved through the streets. It felt alive.\n\n"
                '"We made it," she whispered softly.\n'
                '"Finally," he said.\n\n'
                "They found an inn near the square. The innkeeper was "
                "a large woman with kind eyes. She gave them a room "
                "overlooking the market."
            ),
            chapter_number=3,
            source_path=Path("/fake/chapter-003.md"),
        ),
    ]


# ── Stub LLM ─────────────────────────────────────────────────────────


class StubChatModel(BaseChatModel):
    """Returns deterministic placeholder responses for testing."""

    @property
    def _llm_type(self) -> str:
        return "stub-test"

    def _generate(
        self, messages: list[BaseMessage], **kwargs: object
    ) -> ChatResult:
        text = f"[stub response to {len(messages)} messages]"
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))]
        )

    async def _agenerate(
        self, messages: list[BaseMessage], **kwargs: object
    ) -> ChatResult:
        return self._generate(messages, **kwargs)


@pytest.fixture()
def stub_llm() -> BaseChatModel:
    """A stub LLM that returns placeholder text."""
    return StubChatModel()


# ── Temp project directory ────────────────────────────────────────────


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with .ghostreader/ and config.yaml."""
    project = tmp_path / "test-project"
    project.mkdir()
    (project / ".ghostreader").mkdir()
    (project / "config.yaml").write_text(
        "default_model: stub\ndepth: standard\n",
        encoding="utf-8",
    )
    return project


@pytest.fixture()
def tmp_manuscript_dir(tmp_path: Path) -> Path:
    """Create a temp dir with chapter markdown files."""
    ms_dir = tmp_path / "manuscript"
    ms_dir.mkdir()
    (ms_dir / ".ghostreader").mkdir()

    for i in range(1, 4):
        (ms_dir / f"chapter-{i:03d}.md").write_text(
            f"# Chapter {i}\n\nThis is the content of chapter {i}. "
            f"It has enough text to be meaningful for testing purposes. "
            f"The characters do things and say things.\n\n"
            f'"Hello," said the protagonist. "What a fine day."\n\n'
            f"The end of chapter {i}.",
            encoding="utf-8",
        )

    return ms_dir
