"""Dialogue shape (#21): detector plus the ``ghostreader dialogue`` command end to end."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ghostreader.analyzers.dialogue_shape import detect_dialogue_shape, extract_turns
from ghostreader.cli import app
from ghostreader.report.dialogue_export import analyze_dialogue

runner = CliRunner()

NARRATION = (
    "The corridor smelled of coolant and old coffee, and the lights along the ceiling "
    "flickered in a slow wave that nobody had fixed since the last refit of the ship."
)


def _tennis_chapter(turns: int = 30) -> str:
    """Clean, certain one-liners, no long speech: the AI pattern."""
    lines = ["# Chapter 1", "", NARRATION, ""]
    for i in range(turns):
        who = "Mara" if i % 2 == 0 else "Teo"
        lines += [f'"The relay is down on deck {i}," {who} said.', ""]
    return "\n".join(lines)


def _human_chapter() -> str:
    """Hesitant turns and a long answer between short ones."""
    lines = ["# Chapter 1", "", NARRATION, ""]
    long_answer = (
        '"I went down there because I thought, well, somebody had to, and the hatch was '
        "already open when I got to it, and there was water on the floor, a lot of water, "
        "more than the pumps could ever have let in, so I knew before I even looked that "
        'someone had been inside before me and left in a hurry," Mara said.'
    )
    for i in range(30):
        if i % 6 == 0:
            lines += [long_answer, ""]
        elif i % 3 == 0:
            lines += ['"I don\'t know. Maybe it was the... no."', ""]
        else:
            lines += [f'"Deck {i} is quiet," Teo said.', ""]
    return "\n".join(lines)


def test_extract_turns_reads_curly_and_straight_quotes() -> None:
    paras = ["\u201cWait\u2014I mean, maybe,\u201d she said.", "No speech here.", '"Fine."']
    turns = extract_turns(paras)
    assert turns[1] is None
    first = turns[0]
    assert first is not None
    assert set(first.hesitations) >= {"broken_off", "filler", "hedge"}
    assert turns[2] is not None
    assert turns[2].hesitations == []


def test_tennis_chapter_flags_volley_no_long_speech_and_fluent() -> None:
    report = detect_dialogue_shape(_tennis_chapter(), chapter_number=3)
    kinds = {f.kind: f for f in report.findings}
    assert kinds["volley"].severity == "high"
    assert kinds["volley"].turns == 30
    assert kinds["volley"].chapter == 3
    assert "None of this chapter's turns" in kinds["volley"].summary
    assert kinds["no_long_speech"].severity == "moderate"
    assert kinds["fluent_speech"].severity == "high"
    assert report.stats.hesitant_turn_share == 0.0


def test_human_chapter_stays_quiet() -> None:
    report = detect_dialogue_shape(_human_chapter())
    assert report.findings == []
    assert report.stats.longest_turn_words >= 40
    assert report.stats.hesitant_turn_share > 0.2


def test_few_turns_skip_chapter_rows() -> None:
    report = detect_dialogue_shape(_tennis_chapter(turns=12))
    assert [f.kind for f in report.findings] == ["volley"]


def test_analyze_dialogue_disabled_and_cap() -> None:
    chapters = [{"chapter_number": 1, "content": _tennis_chapter()}]
    assert analyze_dialogue(chapters, enabled=False) == ([], [])
    stats, rows = analyze_dialogue(chapters, cap=1)
    assert len(stats) == 1
    assert len(rows) == 1
    assert rows[0]["kind"] == "volley"
    assert rows[0]["message"] == rows[0]["summary"]


def _story(tmp_path: Path) -> Path:
    story = tmp_path / "story"
    chapters = story / "chapters"
    chapters.mkdir(parents=True)
    (chapters / "chapter-01.md").write_text(_tennis_chapter(), encoding="utf-8")
    (chapters / "chapter-02.md").write_text(_human_chapter(), encoding="utf-8")
    return story


def test_dialogue_cli_json(tmp_path: Path) -> None:
    result = runner.invoke(app, ["dialogue", str(_story(tmp_path)), "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert [c["chapter"] for c in data["chapters"]] == [1, 2]
    rows = data["dialogue_findings"]
    assert {r["chapter"] for r in rows} == {1}
    assert rows[0]["kind"] == "volley"
    assert rows[0]["severity"] == "high"


def test_dialogue_cli_markdown_out(tmp_path: Path) -> None:
    out = tmp_path / "dialogue.md"
    result = runner.invoke(app, ["dialogue", str(_story(tmp_path)), "--out", str(out)])
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert "# Dialogue shape" in text
    assert "| Ch | Turns |" in text
    assert "`fluent_speech`" in text


# -- LLM tennis-return judge (fake model) --------------------------------


class _FakeLLM:
    """Labels every pair whose reply starts with "Not" as an x_not_y retort."""

    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, messages: list) -> object:
        import re as _re

        self.calls += 1
        body = messages[-1].content
        hits = []
        for m in _re.finditer(r"\[(\d+)\]\nA: [^\n]*\nB: ([^\n]*)", body):
            if m.group(2).startswith("Not"):
                hits.append({"id": int(m.group(1)), "form": "x_not_y"})
            elif m.group(2).startswith("No"):
                hits.append({"id": int(m.group(1)), "form": "flat_denial"})

        class _R:
            content = json.dumps(hits)

        return _R()


def _retort_chapter() -> str:
    lines = ["# Chapter 1", ""]
    for i in range(20):
        lines += [f'"The pump on deck {i} is fine," Mara said.', ""]
        reply = f"Not fine. Failing, deck {i}." if i % 2 == 0 else "No. It is broken."
        lines += [f'"{reply}"', "", NARRATION + " " + NARRATION, ""]
    return "\n".join(lines)


def test_judge_reports_recast_forms_only() -> None:
    import asyncio

    from ghostreader.analyzers.dialogue_judge import exchange_pairs, judge_tennis_returns

    text = _retort_chapter()
    assert len(exchange_pairs(text)) == 20
    llm = _FakeLLM()
    rows, stats, warnings = asyncio.run(judge_tennis_returns(llm, text, chapter_number=4))  # type: ignore[arg-type]
    assert warnings == []
    assert stats["pairs"] == 20
    assert stats["tennis_returns"] == 10
    assert stats["forms"] == {"x_not_y": 10, "flat_denial": 10}
    habit = rows[0]
    assert habit["kind"] == "tennis_habit"
    assert habit["severity"] == "high"
    instances = [r for r in rows if r["kind"] == "tennis_return"]
    assert len(instances) == 5
    assert instances[0]["quote"].startswith("The pump on deck 0 is fine, / Not fine.")


def test_dialogue_cli_judge_json(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import ghostreader.llm as llm_mod

    story = tmp_path / "story"
    (story / "chapters").mkdir(parents=True)
    (story / "chapters" / "chapter-01.md").write_text(_retort_chapter(), encoding="utf-8")
    monkeypatch.setattr(llm_mod, "get_llm", lambda *a, **k: _FakeLLM())
    result = runner.invoke(app, ["dialogue", str(story), "--json", "--judge"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["judge"]["book"]["tennis_returns"] == 10
    assert data["dialogue_findings"][0]["kind"] == "tennis_habit"


# -- LLM comedy-source judge (fake model) --------------------------------


class _ComedyLLM:
    """Every scene: three quips, no situation, one unearned laugh."""

    def __init__(self, fail_first: bool = False) -> None:
        self.calls = 0
        self.fail_first = fail_first

    async def ainvoke(self, messages: list) -> object:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("boom")
        payload = [
            {
                "intent": 1,
                "escalation": False,
                "moments": [
                    {"kind": "verbal", "quote": f"Quip {self.calls}a"},
                    {"kind": "verbal", "quote": f"Quip {self.calls}b"},
                    {"kind": "verbal", "quote": f"Quip {self.calls}c"},
                    {"kind": "announced", "quote": "Mara grinned despite herself."},
                ],
            }
        ]

        class _R:
            content = json.dumps(payload)

        return _R()


def _long_chapter(words: int = 2400) -> str:
    paras = ["# Chapter 1", ""]
    while sum(len(p.split()) for p in paras) < words:
        paras += [NARRATION, ""]
    return "\n".join(paras)


def test_comedy_judge_flags_quip_only_humor() -> None:
    import asyncio

    from ghostreader.analyzers.comedy_judge import judge_comedy, scene_windows

    text = _long_chapter()
    assert len(scene_windows(text)) == 2
    llm = _ComedyLLM(fail_first=True)
    rows, stats, warnings = asyncio.run(judge_comedy(llm, text, chapter_number=2))  # type: ignore[arg-type]
    assert len(warnings) == 1
    assert stats["windows"] == 1
    assert stats["moments"]["verbal"] == 3
    # Three quips is under the four-moment floor: no quip row yet.
    assert [r["kind"] for r in rows] == ["announced_levity"]

    rows, stats, warnings = asyncio.run(judge_comedy(_ComedyLLM(), text, chapter_number=2))  # type: ignore[arg-type]
    assert warnings == []
    quip = rows[0]
    assert quip["kind"] == "quip_humor"
    assert quip["severity"] == "high"
    assert quip["quote"].startswith("Quip 1a / ")
    assert [r["kind"] for r in rows[1:]] == ["announced_levity", "announced_levity"]


def test_dialogue_cli_comedy_json(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import ghostreader.llm as llm_mod

    story = tmp_path / "story"
    (story / "chapters").mkdir(parents=True)
    (story / "chapters" / "chapter-01.md").write_text(_long_chapter(), encoding="utf-8")
    monkeypatch.setattr(llm_mod, "get_llm", lambda *a, **k: _ComedyLLM())
    result = runner.invoke(app, ["dialogue", str(story), "--json", "--comedy"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    book = data["comedy"]["book"]
    assert book["moments"]["verbal"] == 6
    assert book["situation_share"] == 0.0
    assert data["dialogue_findings"][0]["kind"] == "quip_humor"
    out = tmp_path / "d.md"
    result = runner.invoke(app, ["dialogue", str(story), "--comedy", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "0% from situation" in out.read_text(encoding="utf-8")
