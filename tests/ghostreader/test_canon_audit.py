"""#16 Phase 2: deterministic Canon audit."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from ghostreader.canon_audit import (
    audit_canon,
    audit_stories,
    audit_story,
    names_in,
    render_audit_markdown,
)
from ghostreader.cli import app
from tests.test_canon_continuity import CH1, CH2, make_story, write_canon


def _w(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _kinds(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["kind"], []).append(r)
    return out


def test_names_in() -> None:
    text = "He went to St. Mary’s. Then Your Damascus and Cole’s Syrian ally met on Harbor Street."
    assert names_in(text, {"your"}) == ["St. Mary", "Harbor Street"]
    assert names_in("The Old Mill of the Valley") == ["Old Mill of the Valley"]


def test_clean_fixture_has_no_concerns(tmp_path: Path) -> None:
    write_canon(tmp_path / "canon")
    rows = audit_canon(tmp_path / "canon", {1: CH1, 2: CH2}, through=2)
    assert [r for r in rows if r["severity"] == "concern"] == []
    # Fixture records settings for chapter 2 only.
    assert {r["kind"] for r in rows} <= {"missing_file", "chapter_not_recorded"}


def test_self_checks(tmp_path: Path) -> None:
    canon = tmp_path / "canon"
    _w(canon / "characters/a.json", {"name": "Ann Lee", "status": "deceased", "died_chapter": 0})
    _w(
        canon / "characters/b.json",
        {"name": "Bo", "status": "deceased", "died_chapter": 2, "last_seen_chapter": 5},
    )
    _w(
        canon / "plot/unresolved-seeds.json",
        [
            {
                "slug": "s1",
                "planted_in_chapter": 1,
                "resolved_in_chapter": 1,
                "priority": "critical",
            },
            {"slug": "s2", "planted_in_chapter": 1, "resolved_in_chapter": 1, "priority": "minor"},
            {"slug": "s3", "planted_in_chapter": 4, "resolved_in_chapter": 2},
        ],
    )
    _w(
        canon / "style/story-timeline.json",
        {
            "chapter_timestamps": [
                {"chapter": c, "narrative_time": "Late August", "end_time": f"Day {c}"}
                for c in (1, 2, 4)
            ]
        },
    )
    _w(canon / "style/physical-state.json", [])
    _w(canon / "style/chapter-ending-states.json", [{"chapter": 1, "ending_state": "x"}])
    k = _kinds(audit_canon(canon, dict.fromkeys(range(1, 5), "Ann Lee and Bo.")))
    assert [r["entity"] for r in k["death_chapter_missing"]] == ["a"]
    assert k["seen_after_death"][0]["chapter"] == 5
    assert [r["entity"] for r in k["seed_resolved_when_planted"]] == ["s1"]
    assert [r["entity"] for r in k["seed_resolved_before_planted"]] == ["s3"]
    vague = k["timeline_vague"]
    assert [r["entity"] for r in vague] == ["narrative_time"]
    assert "3 of 3 chapters say 'Late August'" in vague[0]["summary"]
    assert k["empty_file"][0]["file"] == "style/physical-state.json"
    missing = {r["file"]: r["detail"] for r in k["chapter_not_recorded"]}
    assert missing == {
        "style/story-timeline.json": "3",
        "style/chapter-ending-states.json": "2,3,4",
    }
    assert "plot/secrets-registry.json" in {r["file"] for r in k["missing_file"]}


def test_prose_checks(tmp_path: Path) -> None:
    canon = tmp_path / "canon"
    _w(
        canon / "style/key-facts.json",
        [
            "Setting: The funeral is held at St. Augustine's, a stone church.",
            "Noor Hadid: Siena's sister Lila Cole died young.",  # relative, not drift
            "Harbor Street runs past the dock.",
        ],
    )
    _w(canon / "characters/ghost.json", {"name": "Father Quill", "introduced_chapter": 1})
    _w(canon / "characters/noor.json", {"name": "Noor Hadid", "introduced_chapter": 1})
    prose = {1: "At St. Mary’s, Noor met Siena Cole on Harbor Street. Your Damascus waits."}
    k = _kinds(audit_canon(canon, prose))
    assert [r["summary"] for r in k["name_drift"]] == [
        "Key facts say 'St. Augustine'; the prose says 'St. Mary'"
    ]
    assert [r["entity"] for r in k["character_not_in_prose"]] == ["ghost"]


def test_bad_json_never_raises(tmp_path: Path) -> None:
    canon = tmp_path / "canon"
    (canon / "style").mkdir(parents=True)
    (canon / "style/key-facts.json").write_text("{", encoding="utf-8")
    (canon / "style/story-timeline.json").write_text('{"chapter_timestamps": 3}', encoding="utf-8")
    rows = audit_canon(canon, {1: "x"})
    assert any(r["kind"] == "empty_file" for r in rows)


def test_stories_report_and_cli(tmp_path: Path) -> None:
    make_story(tmp_path)
    (tmp_path / "no-canon/chapters").mkdir(parents=True)
    results = audit_stories(tmp_path)
    assert [r["story"] for r in results] == ["saltmere"]
    assert audit_story(tmp_path / "no-canon") is None
    md = render_audit_markdown(results)
    assert md.startswith("# Canon audit")
    assert "1 stories with Canon and chapters" in md

    runner = CliRunner()
    one = runner.invoke(app, ["canon-audit", str(tmp_path / "saltmere"), "--json"])
    assert one.exit_code == 0, one.output
    assert json.loads(one.output)[0]["story"] == "saltmere"
    out = tmp_path / "report.md"
    many = runner.invoke(app, ["canon-audit", str(tmp_path), "--out", str(out)])
    assert many.exit_code == 0
    assert out.read_text(encoding="utf-8").startswith("# Canon audit")
    none = runner.invoke(app, ["canon-audit", str(tmp_path / "no-canon")])
    assert none.exit_code == 1
