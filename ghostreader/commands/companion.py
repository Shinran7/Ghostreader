"""Companion command orchestrator — CLI thin, logic here."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console

from ghostreader.companion.brief import (
    export_brief_json,
    render_brief_terminal,
    write_brief_files,
)
from ghostreader.companion.discovery import discover
from ghostreader.companion.pipeline import run_companion_pipeline
from ghostreader.config import GhostreaderConfig
from ghostreader.paths import companion_reports_dir, story_state_dir_for

_ERR = Console(stderr=True)


async def run_companion(
    path: Path,
    *,
    chapter: int | None = None,
    output_format: str = "terminal",
    output_path: Path | None = None,
    no_cache: bool = False,
    typesafe: bool | None = None,
    continuity_only: bool = False,
    craft_only: bool = False,
    fail_on_continuity: bool = False,
    model: str | None = None,
    genre: str | None = None,
) -> int:
    """Run companion pipeline. Returns process exit code (0/1/2)."""
    from ghostreader.llm import get_llm, load_secrets
    from ghostreader.typesafe import (
        ensure_typesafe_api_key,
        ensure_typesafe_sdk,
        resolve_typesafe_enabled,
    )
    from ghostreader.typesafe.client import TypesafeConfigError

    path = path.resolve()
    json_mode = (output_format or "terminal").lower() == "json"

    try:
        discovery = discover(path, chapter_override=chapter)
    except FileNotFoundError as exc:
        _ERR.print(f"[red]Error:[/red] {exc}")
        return 1
    except ValueError as exc:
        _ERR.print(f"[red]Error:[/red] {exc}")
        return 1

    cfg = GhostreaderConfig.load(path)
    typesafe_on = resolve_typesafe_enabled(typesafe, cfg)
    load_secrets()

    if typesafe_on:
        try:
            ensure_typesafe_sdk()
            ensure_typesafe_api_key()
        except TypesafeConfigError as exc:
            _ERR.print(f"[red]Error:[/red] {exc}")
            return 1

    llm = get_llm(model, manuscript_path=path)
    if typesafe_on:
        llm_type = getattr(llm, "_llm_type", None)
        if llm_type == "stub" and (model or "").strip().lower() != "stub":
            _ERR.print(
                "[red]Error:[/red] TypeSafe mode still needs a real chat-model API key "
                "for facts, enrich, and the chapter note.\n"
                "  Set the provider key in secrets/llm.env, or pass --no-typesafe / "
                "--model stub (tests only)."
            )
            return 1
        _ERR.print(
            f"[cyan]TypeSafe judgments: on[/cyan] "
            f"(companion gate dims; floor {cfg.typesafe_confidence_floor})"
        )

    if cfg.llm_json_probe:
        from ghostreader.llm import probe_json_contract

        _ERR.print("[cyan]Probing LLM JSON contract...[/cyan]")
        probe_ok, probe_detail = await probe_json_contract(llm)
        if not probe_ok:
            _ERR.print(
                "[bold red]Aborting:[/bold red] Chat model failed the JSON contract probe "
                "after normalization + one repair retry.\n"
                "  Companion continuity would run on empty fact sheets.\n"
                "  Switch models, fix provider wiring, or set llm_json_probe: false "
                "(not recommended).\n"
                f"  Probe reply was: {probe_detail[:300]!r}"
            )
            return 1
        _ERR.print("[green]LLM JSON probe:[/green] ok")

    effective_genre = genre or discovery.seed_meta.get("genre") or cfg.genre
    story_state = story_state_dir_for(path)

    try:
        if typesafe_on:
            from typesafe_sdk import AsyncTypeSafeClient

            async with AsyncTypeSafeClient() as typesafe_client:
                brief = await run_companion_pipeline(
                    discovery,
                    llm=llm,
                    typesafe_client=typesafe_client,
                    typesafe_enabled=True,
                    story_state_dir=story_state,
                    genre=effective_genre,
                    no_cache=no_cache,
                    continuity_only=continuity_only,
                    craft_only=craft_only,
                    companion_prior=cfg.companion_prior,
                    companion_rolling_min_chapters=cfg.companion_rolling_min_chapters,
                    companion_fact_chars_budget=cfg.companion_fact_chars_budget,
                    companion_craft_window=cfg.companion_craft_window,
                    companion_cross_chapter_craft=cfg.companion_cross_chapter_craft,
                    companion_info_dims=cfg.companion_info_dims,
                    companion_light_narrative=cfg.companion_light_narrative,
                    companion_register_watch=cfg.companion_register_watch,
                    typesafe_confidence_floor=cfg.typesafe_confidence_floor,
                    typesafe_noul_positive_threshold=cfg.typesafe_noul_positive_threshold,
                    json_mode=json_mode,
                )
        else:
            brief = await run_companion_pipeline(
                discovery,
                llm=llm,
                typesafe_client=None,
                typesafe_enabled=False,
                story_state_dir=story_state,
                genre=effective_genre,
                no_cache=no_cache,
                continuity_only=continuity_only,
                craft_only=craft_only,
                companion_prior=cfg.companion_prior,
                companion_rolling_min_chapters=cfg.companion_rolling_min_chapters,
                companion_fact_chars_budget=cfg.companion_fact_chars_budget,
                companion_craft_window=cfg.companion_craft_window,
                companion_cross_chapter_craft=cfg.companion_cross_chapter_craft,
                companion_info_dims=cfg.companion_info_dims,
                companion_light_narrative=cfg.companion_light_narrative,
                companion_register_watch=cfg.companion_register_watch,
                typesafe_confidence_floor=cfg.typesafe_confidence_floor,
                typesafe_noul_positive_threshold=cfg.typesafe_noul_positive_threshold,
                json_mode=json_mode,
            )
    except Exception as exc:  # noqa: BLE001
        _ERR.print(f"[red]Error:[/red] Companion failed: {exc}")
        return 1

    try:
        reports_dir = companion_reports_dir(story_state)
        md_path = write_brief_files(brief, reports_dir, also_path=output_path)
        _ERR.print(f"[green]Brief saved:[/green] {md_path}")

        if json_mode:
            # Stdout = JSON only
            export_brief_json(brief, output=sys.stdout)
        else:
            render_brief_terminal(brief)
    except Exception as exc:  # noqa: BLE001
        _ERR.print(f"[red]Error:[/red] Failed to write companion brief: {exc}")
        return 1

    fact_parse_poisoned = any(
        w.startswith("Fact extraction JSON parse failed") for w in brief.warnings
    )
    if fact_parse_poisoned and cfg.abort_on_fact_parse_failure and not craft_only:
        _ERR.print(
            "[bold red]Exiting 1:[/bold red] Fact extraction JSON parse failures "
            "poisoned continuity. Brief was still written (verdict=watch). "
            "Set abort_on_fact_parse_failure: false to treat as soft watch only."
        )
        return 1

    if fail_on_continuity and any(f.severity == "concern" for f in brief.continuity_findings):
        return 2
    return 0


__all__ = ["run_companion"]
