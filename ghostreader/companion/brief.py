"""CompanionBrief model and terminal / markdown / JSON renderers."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TextIO

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ghostreader import __version__ as PACKAGE_VERSION
from ghostreader.report import (
    DimensionRating,
    PrioritizedFinding,
    severity_color,
    severity_emoji,
)

# Companion brief JSON contract (independent of package __version__ / analyze).
GHOSTREADER_VERSION = "0.2.2"


@dataclass
class CompanionBrief:
    """Ship-it / watch-this brief for Autonomicon hooks."""

    manuscript_name: str
    story_slug: str
    mode: Literal["progressive", "sweep"]
    chapter_number: int
    chapters_considered: list[int]
    facts_reused: int
    facts_extracted: int
    verdict: Literal["ship", "watch"]
    chapter_note: str
    continuity_findings: list[PrioritizedFinding] = field(default_factory=list)
    preexisting_continuity_findings: list[PrioritizedFinding] = field(default_factory=list)
    ungrounded_continuity_findings: list[PrioritizedFinding] = field(default_factory=list)
    craft_findings: list[PrioritizedFinding] = field(default_factory=list)
    craft_ratings: list[DimensionRating] = field(default_factory=list)
    continuity_ratings: list[DimensionRating] = field(default_factory=list)
    craft_window_chapters: list[int] = field(default_factory=list)
    info_continuity_findings: list[PrioritizedFinding] = field(default_factory=list)
    info_continuity_ratings: list[DimensionRating] = field(default_factory=list)
    narrative_findings: list[PrioritizedFinding] = field(default_factory=list)
    narrative_ratings: list[DimensionRating] = field(default_factory=list)
    verdict_drivers: list[str] = field(default_factory=list)
    repetition_findings: list[dict[str, Any]] = field(default_factory=list)
    # Machine register / initiation rows (JSON-primary; empty OK). Kinds:
    # unearned_jargon | initiation_budget only (no missing_human_door).
    register_findings: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ungrounded_count: int = 0
    typesafe_enabled: bool = False
    generated_at: str = ""


def compute_verdict(
    continuity_findings: list[PrioritizedFinding],
    craft_findings: list[PrioritizedFinding],
    narrative_findings: list[PrioritizedFinding] | None = None,
) -> Literal["ship", "watch"]:
    if any(f.severity == "concern" for f in continuity_findings):
        return "watch"
    if any(f.severity == "concern" for f in craft_findings):
        return "watch"
    if narrative_findings and any(f.severity == "concern" for f in narrative_findings):
        return "watch"
    return "ship"


def compute_verdict_drivers(
    continuity_findings: list[PrioritizedFinding],
    craft_findings: list[PrioritizedFinding],
    narrative_findings: list[PrioritizedFinding] | None = None,
) -> list[str]:
    """Which bands contributed a concern (continuity / craft / narrative)."""
    drivers: list[str] = []
    if any(f.severity == "concern" for f in continuity_findings):
        drivers.append("continuity")
    if any(f.severity == "concern" for f in craft_findings):
        drivers.append("craft")
    if narrative_findings and any(f.severity == "concern" for f in narrative_findings):
        drivers.append("narrative")
    return drivers


def finding_from_dict(raw: dict[str, Any], *, rank: int) -> PrioritizedFinding:
    return PrioritizedFinding(
        rank=int(raw.get("rank") or rank),
        dimension=str(raw.get("dimension") or ""),
        severity=str(raw.get("severity") or "neutral"),
        summary=str(raw.get("summary") or ""),
        evidence=str(raw.get("evidence") or ""),
        chapter_ref=str(raw.get("chapter_ref") or ""),
        counter_evidence=str(raw.get("counter_evidence") or ""),
    )


def findings_from_dicts(raws: list[dict[str, Any]]) -> list[PrioritizedFinding]:
    return [finding_from_dict(r, rank=i + 1) for i, r in enumerate(raws)]


def rating_from_dict(raw: dict[str, Any]) -> DimensionRating:
    return DimensionRating(
        dimension=str(raw.get("dimension") or ""),
        severity=str(raw.get("severity") or "neutral"),
        note=str(raw.get("note") or ""),
    )


def brief_to_payload(brief: CompanionBrief) -> dict[str, Any]:
    """JSON-serializable dict matching the Autonomicon hook contract."""
    generated = brief.generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "ghostreader_version": GHOSTREADER_VERSION,
        "package_version": PACKAGE_VERSION,
        "mode": brief.mode,
        "generated_at": generated,
        "manuscript_name": brief.manuscript_name,
        "story_slug": brief.story_slug,
        "chapter_number": brief.chapter_number,
        "chapters_considered": list(brief.chapters_considered),
        "facts_reused": brief.facts_reused,
        "facts_extracted": brief.facts_extracted,
        "verdict": brief.verdict,
        "chapter_note": brief.chapter_note,
        "continuity_findings": [asdict(f) for f in brief.continuity_findings],
        "preexisting_continuity_findings": [
            asdict(f) for f in brief.preexisting_continuity_findings
        ],
        "ungrounded_continuity_findings": [asdict(f) for f in brief.ungrounded_continuity_findings],
        "craft_findings": [asdict(f) for f in brief.craft_findings],
        "continuity_ratings": [asdict(r) for r in brief.continuity_ratings],
        "craft_ratings": [asdict(r) for r in brief.craft_ratings],
        "craft_window_chapters": list(brief.craft_window_chapters),
        "info_continuity_findings": [asdict(f) for f in brief.info_continuity_findings],
        "info_continuity_ratings": [asdict(r) for r in brief.info_continuity_ratings],
        "narrative_findings": [asdict(f) for f in brief.narrative_findings],
        "narrative_ratings": [asdict(r) for r in brief.narrative_ratings],
        "verdict_drivers": list(brief.verdict_drivers),
        "repetition_findings": list(brief.repetition_findings),
        "register_findings": list(brief.register_findings),
        "warnings": list(brief.warnings),
        "ungrounded_count": brief.ungrounded_count,
        "typesafe_enabled": brief.typesafe_enabled,
    }


def export_brief_json(
    brief: CompanionBrief,
    *,
    output: TextIO | None = None,
    indent: int = 2,
) -> str:
    """Write one JSON document to stdout (or *output*). No Rich."""
    text = json.dumps(brief_to_payload(brief), indent=indent, ensure_ascii=False)
    stream = output if output is not None else sys.stdout
    stream.write(text + "\n")
    return text


def _format_finding_md(f: PrioritizedFinding, *, ungrounded: bool = False) -> str:
    mark = severity_emoji(f.severity)
    ref = f" {f.chapter_ref}:" if f.chapter_ref else ":"
    lines = [f"- {mark} [{f.severity}]{ref} {f.summary}"]
    ev = (f.evidence or "").strip()
    counter = (f.counter_evidence or "").strip()
    if ungrounded and (not ev or not counter):
        lines.append("  _(citations unavailable — not used for ship gate)_")
    else:
        if ev:
            lines.append(f"  > {ev}")
        if counter:
            lines.append(f"  > **vs.** {counter}")
    return "\n".join(lines)


def render_brief_markdown(brief: CompanionBrief) -> str:
    """Markdown brief (continuity first)."""
    verdict = brief.verdict.upper()
    reused = brief.facts_reused
    extracted = brief.facts_extracted
    chs = brief.chapters_considered
    ch_span = f"chapters {chs[0]}–{chs[-1]}" if chs else "no chapters"
    lines = [
        f"# Companion — {brief.manuscript_name}",
        "",
        f"**Verdict:** {verdict}",
        f"**Prior facts:** {reused} reused, {extracted} extracted · {ch_span}",
        "",
        "## Chapter note",
        brief.chapter_note or "_(none)_",
        "",
    ]

    if brief.mode == "progressive":
        lines.append("## Continuity (this chapter — primary)")
    else:
        lines.append("## Continuity (full story — primary)")
    if brief.continuity_findings:
        lines.extend(_format_finding_md(f) for f in brief.continuity_findings)
    else:
        lines.append("- _(none)_")
    lines.append("")

    lines.append("## Continuity (ungrounded — not gating)")
    if brief.ungrounded_continuity_findings:
        lines.extend(
            _format_finding_md(f, ungrounded=True) for f in brief.ungrounded_continuity_findings
        )
    else:
        lines.append("- _(none)_")
    lines.append("")

    if brief.mode == "progressive":
        lines.append("## Pre-existing continuity (not this chapter’s gate)")
        if brief.preexisting_continuity_findings:
            lines.extend(_format_finding_md(f) for f in brief.preexisting_continuity_findings)
        else:
            lines.append("- _(none)_")
        lines.append("")

    lines.append("## Continuity watches (not gating)")
    if brief.info_continuity_findings:
        lines.extend(_format_finding_md(f) for f in brief.info_continuity_findings)
    else:
        lines.append("- _(none)_")
    lines.append("")

    lines.append(f"## Craft (chapter {brief.chapter_number})")
    if brief.craft_findings:
        lines.extend(_format_finding_md(f) for f in brief.craft_findings)
    else:
        lines.append("- _(none)_")
    lines.append("")

    # Narrative section only when the light narrative pass ran.
    if brief.narrative_findings or brief.narrative_ratings:
        lines.append(f"## Narrative (chapter {brief.chapter_number} — light)")
        if brief.narrative_findings:
            lines.extend(_format_finding_md(f) for f in brief.narrative_findings)
        else:
            lines.append("- _(none)_")
        lines.append("")

    if brief.warnings:
        lines.append("## Warnings")
        lines.extend(f"- {w}" for w in brief.warnings)
        lines.append("")

    checklist = [
        "## Ship checklist",
        "- [ ] Continuity concerns for this chapter addressed (or accepted)",
        "- [ ] Continuity watches acknowledged (foreshadowing / unresolved)",
        "- [ ] Craft watches acknowledged",
    ]
    if brief.narrative_findings or brief.narrative_ratings:
        checklist.append("- [ ] Narrative watches acknowledged (pacing / arcs)")
    checklist.append("")
    lines.extend(checklist)
    return "\n".join(lines)


def render_brief_terminal(brief: CompanionBrief, *, console: Console | None = None) -> None:
    """Rich panel with verdict color; continuity section first."""
    console = console or Console()
    color = "green" if brief.verdict == "ship" else "yellow"
    header = Text.assemble(
        ("Verdict: ", "bold"),
        (brief.verdict.upper(), f"bold {color}"),
        (
            f"  ·  {brief.facts_reused} facts reused, {brief.facts_extracted} extracted",
            "dim",
        ),
    )
    console.print(Panel(header, title=f"Companion — {brief.manuscript_name}"))

    if brief.warnings:
        for w in brief.warnings:
            console.print(f"[yellow]Warning:[/yellow] {w}")

    console.print(f"\n[bold]Chapter note[/bold]\n{brief.chapter_note or '(none)'}\n")

    def _print_findings(
        title: str, findings: list[PrioritizedFinding], *, ungrounded: bool = False
    ) -> None:
        console.print(f"[bold]{title}[/bold]")
        if not findings:
            console.print("  (none)")
            return
        for f in findings:
            style = severity_color(f.severity)
            ref = f" {f.chapter_ref}" if f.chapter_ref else ""
            console.print(
                f"  [{style}]{severity_emoji(f.severity)} [{f.severity}]{ref}:[/{style}] {f.summary}"
            )
            if ungrounded and (
                not (f.evidence or "").strip() or not (f.counter_evidence or "").strip()
            ):
                console.print("    [dim](citations unavailable — not used for ship gate)[/dim]")
            else:
                if f.evidence:
                    console.print(f"    > {f.evidence}")
                if f.counter_evidence:
                    console.print(f"    > vs. {f.counter_evidence}")

    cont_title = (
        "Continuity (this chapter)" if brief.mode == "progressive" else "Continuity (full story)"
    )
    _print_findings(cont_title, brief.continuity_findings)
    _print_findings(
        "Continuity (ungrounded)",
        brief.ungrounded_continuity_findings,
        ungrounded=True,
    )
    if brief.mode == "progressive":
        _print_findings(
            "Pre-existing continuity",
            brief.preexisting_continuity_findings,
        )
    _print_findings("Continuity watches (not gating)", brief.info_continuity_findings)
    _print_findings(f"Craft (chapter {brief.chapter_number})", brief.craft_findings)
    if brief.narrative_findings or brief.narrative_ratings:
        _print_findings(
            f"Narrative (chapter {brief.chapter_number} — light)",
            brief.narrative_findings,
        )


def write_brief_files(
    brief: CompanionBrief,
    reports_dir: Path,
    *,
    also_path: Path | None = None,
) -> Path:
    """Write markdown (+ JSON sibling) under companion/reports/."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if brief.mode == "sweep" and "Sweep" in brief.manuscript_name:
        base = f"companion-sweep-{today}"
    else:
        base = f"companion-ch{brief.chapter_number:03d}-{today}"

    md_path = reports_dir / f"{base}.md"
    n = 2
    while md_path.exists():
        md_path = reports_dir / f"{base}-{n}.md"
        n += 1

    md_text = render_brief_markdown(brief)
    md_path.write_text(md_text, encoding="utf-8")
    json_path = md_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(brief_to_payload(brief), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if also_path is not None:
        also_path = also_path.resolve()
        also_path.parent.mkdir(parents=True, exist_ok=True)
        also_path.write_text(md_text, encoding="utf-8")

    return md_path


__all__ = [
    "GHOSTREADER_VERSION",
    "CompanionBrief",
    "brief_to_payload",
    "compute_verdict",
    "compute_verdict_drivers",
    "export_brief_json",
    "finding_from_dict",
    "findings_from_dicts",
    "rating_from_dict",
    "render_brief_markdown",
    "render_brief_terminal",
    "write_brief_files",
]
