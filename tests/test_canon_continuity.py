"""#16: Canon as the continuity state of record (companion + analyze).

The fixture story plants four contradictions in chapter 3 against Canon as of
chapter 2: a forgotten broken arm, a key reused after it was lost, time
running backward, and a dead character speaking. The fake LLM finds each
planted fact in the state block it is sent and cites that entry's id, so the
tests prove the state block carries the facts and the pipeline grounds and
gates the findings.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from ghostreader.agents.consistency_checker import scene_consistency_checker_node
from ghostreader.agents.synthesis import _continuity_source
from ghostreader.companion.brief import brief_to_payload
from ghostreader.companion.discovery import DiscoveryResult
from ghostreader.companion.pipeline import run_companion_pipeline
from ghostreader.companion.progress import ProgressState
from ghostreader.ingestion import Chapter
from ghostreader.report import ReportOutput
from ghostreader.report.json_export import _build_payload

CH1 = (
    "Mara found the brass key in her father's coat.\n\n"
    "Old Tom watched her from the dock and said nothing."
)
CH2 = (
    "The storm broke the mast. Mara fell and her left arm snapped under her.\n\n"
    "She threw the brass key into the harbor. Old Tom drowned before dawn."
)
CH3 = (
    "That morning, before the storm, Mara woke early.\n\n"
    "She gripped the rope with her left arm and hauled herself up the cliff.\n\n"
    "At the top she unlocked the cellar door with the brass key.\n\n"
    "“You took your time,” Old Tom said, and handed her a lantern."
)

# Planted fact (as it appears in the state block) -> evidence quote in CH3.
PLANTED = {
    "left_arm": ("consistency.character", "Ch 3: 'She gripped the rope with her left arm'"),
    "brass_key": (
        "consistency.plot_holes",
        "Ch 3: 'she unlocked the cellar door with the brass key'",
    ),
    "Night, Day 2": (
        "consistency.timeline",
        "Ch 3: 'That morning, before the storm, Mara woke early.'",
    ),
    "Old Tom": ("consistency.character", "Ch 3: '“You took your time,” Old Tom said'"),
}


def _w(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def write_canon(canon: Path, *, through: int = 2) -> None:
    """Canon after chapter ``through`` (live) — includes a chapter-3 row to filter."""
    _w(
        canon / "characters/mara.json",
        {
            "slug": "mara",
            "name": "Mara",
            "role": "protagonist",
            "status": "active",
            "pronouns": "she/her",
            "introduced_chapter": 1,
            "weight": "protagonist",
        },
    )
    _w(
        canon / "characters/old-tom.json",
        {
            "slug": "old-tom",
            "name": "Old Tom",
            "role": "mentor",
            "status": "deceased",
            "died_chapter": 2,
            "introduced_chapter": 1,
            "last_seen_chapter": 2,
            "last_seen_location": "the harbor",
            "pronouns": "he/him",
        },
    )
    _w(
        canon / "characters/late-comer.json",
        {
            "slug": "late-comer",
            "name": "Late Comer",
            "status": "active",
            "introduced_chapter": 3,
        },
    )
    _w(
        canon / "style/physical-state.json",
        [
            {
                "entity": "mara",
                "attribute": "injuries.left_arm",
                "value": "fractured, splinted",
                "chapter": 2,
                "progression": "worsening",
            },
            {
                "entity": "mara",
                "attribute": "object_locations.brass_key",
                "value": "in her coat",
                "chapter": 1,
                "progression": "stable",
            },
            {
                "entity": "mara",
                "attribute": "object_locations.brass_key",
                "value": "thrown into the harbor, lost",
                "chapter": 2,
                "progression": "stable",
            },
            {"entity": "mara", "attribute": "injuries.ribs", "value": "bruised", "chapter": 3},
        ],
    )
    _w(
        canon / "style/story-timeline.json",
        {
            "chapter_timestamps": [
                {
                    "chapter": 1,
                    "narrative_time": "Evening, Day 1",
                    "end_time": "Late evening, Day 1",
                },
                {
                    "chapter": 2,
                    "narrative_time": "Night, Day 1",
                    "end_time": "Night, Day 2",
                    "elapsed": "24 hours",
                },
            ]
        },
    )
    _w(
        canon / "style/chapter-ending-states.json",
        [
            {"chapter": 1, "ending_state": "Mara on the dock with the key."},
            {"chapter": 2, "ending_state": "Mara ashore, arm broken, Tom drowned."},
        ],
    )
    _w(canon / "style/chapter-locations.json", [{"chapter": 2, "settings": ["the harbor"]}])
    _w(canon / "style/key-facts.json", ["The village is called Saltmere"])
    _w(canon / "world/physics-rules.json", [{"name": "No magic", "description": "No magic"}])
    _w(
        canon / "plot/unresolved-seeds.json",
        [
            {
                "slug": "cellar",
                "description": "What is in the cellar?",
                "planted_in_chapter": 1,
                "resolved_in_chapter": None,
                "priority": "critical",
            },
            {
                "slug": "coat",
                "description": "Whose coat?",
                "planted_in_chapter": 1,
                "resolved_in_chapter": 2,
            },
        ],
    )
    _w(
        canon / "plot/secrets-registry.json",
        [
            {
                "slug": "will",
                "name": "The will",
                "description_summary": "Tom left Mara the cellar",
                "state": "hidden",
                "knowers": ["old-tom"],
                "planted_chapter": 1,
            },
        ],
    )


def make_story(tmp_path: Path) -> Path:
    story = tmp_path / "saltmere"
    chapters = story / "chapters"
    chapters.mkdir(parents=True)
    for n, text in ((1, CH1), (2, CH2), (3, CH3)):
        (chapters / f"chapter-{n:03d}.md").write_text(text, encoding="utf-8")
    write_canon(story / "canon")
    return story


def canon_llm(*, invent_ref: bool = False) -> MagicMock:
    """Fake checker: cite the state entry that holds each planted fact."""

    async def ainvoke(messages: list[Any]) -> AIMessage:
        user = messages[-1].content
        block = user.split("## Chapter", 1)[0]
        findings = []
        for needle, (dim, evidence) in PLANTED.items():
            line = next((ln for ln in block.splitlines() if needle in ln), None)
            ref = re.match(r"\[(\w+)\]", line).group(1) if line else None  # type: ignore[union-attr]
            if ref is None:
                continue
            findings.append(
                {
                    "dimension": dim,
                    "severity": "concern",
                    "summary": f"Chapter 3 contradicts {needle}",
                    "evidence": evidence,
                    "canon_ref": "Z9" if invent_ref else ref,
                    "chapter_ref": "3",
                }
            )
        return AIMessage(content=json.dumps(findings))

    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=ainvoke)
    return llm


def _discovery(story: Path) -> DiscoveryResult:
    chapters_dir = story / "chapters"
    chapters = [
        Chapter(
            title=f"C{n}",
            content=t,
            chapter_number=n,
            source_path=chapters_dir / f"chapter-{n:03d}.md",
        )
        for n, t in ((1, CH1), (2, CH2), (3, CH3))
    ]
    return DiscoveryResult(
        mode="progressive",
        path=chapters_dir,
        story_slug="saltmere",
        story_dir=story,
        chapters_dir=chapters_dir,
        chapter_number=3,
        chapters=chapters,
        gaps=[],
        warnings=[],
        seed_meta={},
        manuscript_name="saltmere · Chapter 3",
    )


async def _companion(story: Path, llm: Any, **kw: Any):
    store = MagicMock()
    store.ensure_facts = AsyncMock(return_value=[])
    store.last_reused = store.last_extracted = 0
    facts_path = AsyncMock(return_value=([], {}, {}))
    with (
        patch("ghostreader.companion.pipeline.FactMemoryStore", return_value=store),
        patch("ghostreader.companion.pipeline._run_llm_consistency", new=facts_path),
        patch("ghostreader.companion.pipeline._chapter_note", new=AsyncMock(return_value="n")),
        patch("ghostreader.companion.pipeline.update_progress_after_run", return_value=None),
        patch(
            "ghostreader.companion.pipeline.clamp_progress_to_disk", return_value=ProgressState()
        ),
        patch("ghostreader.companion.pipeline.compute_order_warnings", return_value=[]),
    ):
        brief = await run_companion_pipeline(
            _discovery(story),
            llm=llm,
            typesafe_client=None,
            typesafe_enabled=False,
            story_state_dir=story / ".gr",
            genre=None,
            continuity_only=True,
            companion_light_narrative=False,
            json_mode=True,
            **kw,
        )
    return brief, facts_path


# --- companion ------------------------------------------------------------


@pytest.mark.asyncio
async def test_companion_catches_planted_contradictions(tmp_path: Path) -> None:
    brief, facts_path = await _companion(make_story(tmp_path), canon_llm())
    facts_path.assert_not_awaited()
    assert brief.continuity_source == "canon"
    assert brief.canon_stats["from_checkpoint"] == 0
    assert brief.verdict == "watch"
    assert len(brief.continuity_findings) == 4
    for f in brief.continuity_findings:
        assert f.quote_verified is True
        assert f.counter_source == "canon"
        assert f.counter_evidence.startswith("Canon ")
        assert f.canon_ref
        assert f.canon_ref["id"]
        assert f.location
        assert f.location["chapter"] == 3
    kinds = {f.canon_ref["kind"] for f in brief.continuity_findings}  # type: ignore[index]
    assert kinds == {"physical state", "item location", "timeline", "character"}
    payload = brief_to_payload(brief)
    assert payload["continuity_source"] == "canon"
    assert payload["continuity_findings"][0]["canon_ref"]["file"]


@pytest.mark.asyncio
async def test_companion_sends_prose_and_filtered_state(tmp_path: Path) -> None:
    llm = canon_llm()
    await _companion(make_story(tmp_path), llm)
    user = llm.ainvoke.await_args.args[0][-1].content
    assert "She gripped the rope with her left arm" in user  # chapter prose, not facts
    assert "thrown into the harbor, lost" in user  # latest key location wins
    assert "in her coat" not in user
    assert "Late Comer" not in user
    assert "bruised" not in user
    assert "deceased since Ch 2" in user
    assert "What is in the cellar?" in user
    assert "Whose coat?" not in user


@pytest.mark.asyncio
async def test_unknown_canon_ref_never_gates(tmp_path: Path) -> None:
    brief, _ = await _companion(make_story(tmp_path), canon_llm(invent_ref=True))
    assert brief.continuity_findings == []
    assert brief.verdict == "ship"
    assert len(brief.ungrounded_continuity_findings) == 4


@pytest.mark.asyncio
async def test_no_canon_falls_back_to_facts(tmp_path: Path) -> None:
    story = make_story(tmp_path)
    for p in sorted((story / "canon").rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
    (story / "canon").rmdir()
    brief, facts_path = await _companion(story, canon_llm())
    facts_path.assert_awaited_once()
    assert brief.continuity_source == "facts"
    assert brief.canon_stats == {}


@pytest.mark.asyncio
async def test_kill_switch_uses_facts(tmp_path: Path) -> None:
    brief, facts_path = await _companion(make_story(tmp_path), canon_llm(), continuity_canon=False)
    facts_path.assert_awaited_once()
    assert brief.continuity_source == "facts"


# --- analyze --------------------------------------------------------------

FACT = {
    "chapter_number": 1,
    "characters": [],
    "location": "dock",
    "timeline_markers": [],
    "established_facts": ["x"],
    "key_objects": [],
}


def _analyze_state(story: Path, **config: Any) -> dict[str, Any]:
    chapters_dir = story / "chapters"
    return {
        "chapters": [
            {
                "chapter_number": n,
                "title": f"C{n}",
                "content": t,
                "source_path": str(chapters_dir / f"chapter-{n:03d}.md"),
            }
            for n, t in ((1, CH1), (2, CH2), (3, CH3))
        ],
        "scene_facts": [],
        "config": config,
    }


@pytest.mark.asyncio
async def test_analyze_checks_each_chapter_against_canon(tmp_path: Path) -> None:
    llm = canon_llm()
    out = await scene_consistency_checker_node(_analyze_state(make_story(tmp_path)), llm)  # type: ignore[arg-type]
    cons = out["consistency_output"]
    assert cons["continuity_source"] == "canon"
    # Chapter 1 still has key facts and rules; every chapter is checked.
    assert cons["canon_stats"]["chapters"] == 3
    assert llm.ainvoke.await_count == 3
    ch3 = [f for f in cons["findings"] if "3" in str(f.get("chapter_ref"))]
    assert {f["dimension"] for f in ch3} >= {"consistency.character", "consistency.timeline"}
    assert all(f.get("counter_source") == "canon" for f in ch3)
    assert _continuity_source(out)["continuity_source"] == "canon"  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_analyze_without_canon_uses_facts(tmp_path: Path) -> None:
    story = tmp_path / "plain"
    (story / "chapters").mkdir(parents=True)
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="[]"))
    state = _analyze_state(story)
    state["scene_facts"] = [FACT]
    out = await scene_consistency_checker_node(state, llm)  # type: ignore[arg-type]
    assert out["consistency_output"]["continuity_source"] == "facts"


@pytest.mark.asyncio
async def test_analyze_kill_switch(tmp_path: Path) -> None:
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="[]"))
    state = _analyze_state(make_story(tmp_path), continuity_canon=False)
    state["scene_facts"] = [FACT]
    out = await scene_consistency_checker_node(state, llm)  # type: ignore[arg-type]
    assert out["consistency_output"]["continuity_source"] == "facts"


def test_analyze_payload_carries_source() -> None:
    report = ReportOutput.from_final_report(
        {
            "executive_summary": "s",
            "prioritized_findings": [
                {
                    "rank": 1,
                    "dimension": "consistency.character",
                    "severity": "concern",
                    "summary": "x",
                    "evidence": "Ch 3: 'a'",
                    "chapter_ref": "2 vs 3",
                    "counter_evidence": "Canon Ch 2 (character): Old Tom deceased",
                    "counter_source": "canon",
                    "canon_ref": {"id": "C2", "kind": "character"},
                }
            ],
            "continuity_source": "canon",
            "canon_stats": {"chapters": 3},
        },
        manuscript_name="book",
    )
    payload = _build_payload(report)
    assert payload["continuity_source"] == "canon"
    assert payload["canon_stats"] == {"chapters": 3}
    assert payload["prioritized_findings"][0]["canon_ref"]["id"] == "C2"
