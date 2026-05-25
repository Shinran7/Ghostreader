"""Ghostreader CLI — AI literary analysis tool for fiction manuscripts."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table

from ghostreader.config import GhostreaderConfig

app = typer.Typer(
    name="ghostreader",
    help="AI literary analysis tool for fiction manuscripts.",
    no_args_is_help=True,
)

config_app = typer.Typer(help="View or edit project configuration.")
app.add_typer(config_app, name="config")

# ── Common option types ──────────────────────────────────────────────

DepthOption = Annotated[
    Optional[str],
    typer.Option(
        "--depth",
        help="Analysis depth: quick, standard, or deep.",
    ),
]
GenreOption = Annotated[
    Optional[str],
    typer.Option("--genre", help="Genre lens (e.g. literary, fantasy, thriller)."),
]
ModelOption = Annotated[
    Optional[str],
    typer.Option("--model", help="Override default LLM model."),
]
FormatOption = Annotated[
    Optional[str],
    typer.Option("--format", help="Output format: markdown or json."),
]
NoCacheOption = Annotated[
    bool,
    typer.Option("--no-cache", help="Force fresh analysis, ignoring cached results."),
]


# ── Commands ─────────────────────────────────────────────────────────


@app.command()
def init(
    project_name: Annotated[str, typer.Argument(help="Name for the new project.")],
) -> None:
    """Create a new Ghostreader project folder with config and state directory."""
    project_dir = Path.cwd() / project_name

    if project_dir.exists():
        rprint(f"[red]Error:[/red] Directory '{project_name}' already exists.")
        raise typer.Exit(code=1)

    project_dir.mkdir(parents=True)
    state_dir = project_dir / ".ghostreader"
    state_dir.mkdir()

    cfg = GhostreaderConfig()
    config_path = cfg.save(project_dir)

    rprint(Panel(f"[green]Project created:[/green] {project_dir}\n"
                 f"  Config: {config_path}\n"
                 f"  State:  {state_dir}",
                 title="ghostreader init"))


@app.command()
def analyze(
    path: Annotated[Path, typer.Argument(help="Path to .md/.epub file or directory.")],
    depth: DepthOption = None,
    genre: GenreOption = None,
    model: ModelOption = None,
    format: FormatOption = None,
    no_cache: NoCacheOption = False,
) -> None:
    """Analyze a manuscript file or directory of chapter files."""
    rprint("Analysis not yet implemented")


@app.command()
def chat(
    project: Annotated[str, typer.Argument(help="Project name to chat about.")],
) -> None:
    """Interactive follow-up chat with a previous analysis."""
    rprint("Chat not yet implemented")


@app.command()
def compare(
    path1: Annotated[Path, typer.Argument(help="First manuscript path.")],
    path2: Annotated[Path, typer.Argument(help="Second manuscript path.")],
    depth: DepthOption = None,
    genre: GenreOption = None,
    model: ModelOption = None,
    format: FormatOption = None,
    no_cache: NoCacheOption = False,
) -> None:
    """Compare two manuscripts with a side-by-side quality scorecard."""
    rprint("Compare not yet implemented")


# ── Config sub-commands ──────────────────────────────────────────────


@config_app.callback(invoke_without_command=True)
def config_show(ctx: typer.Context) -> None:
    """View current project configuration."""
    if ctx.invoked_subcommand is not None:
        return

    project_dir = _find_project_dir()
    if project_dir is None:
        rprint("[red]Error:[/red] No Ghostreader project found in current directory tree.")
        raise typer.Exit(code=1)

    cfg = GhostreaderConfig.load(project_dir)

    table = Table(title=f"Config — {project_dir.name}")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")

    for key, value in cfg.model_dump().items():
        table.add_row(key, str(value))

    rprint(table)


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Config key to set.")],
    value: Annotated[str, typer.Argument(help="New value.")],
) -> None:
    """Set a configuration value."""
    project_dir = _find_project_dir()
    if project_dir is None:
        rprint("[red]Error:[/red] No Ghostreader project found in current directory tree.")
        raise typer.Exit(code=1)

    cfg = GhostreaderConfig.load(project_dir)
    data = cfg.model_dump()

    if key not in data:
        rprint(f"[red]Error:[/red] Unknown config key '{key}'.")
        rprint(f"Valid keys: {', '.join(data.keys())}")
        raise typer.Exit(code=1)

    # Coerce value to the right type
    current = data[key]
    if isinstance(current, list):
        coerced = [v.strip() for v in value.split(",")]
    elif isinstance(current, bool):
        coerced = value.lower() in ("true", "1", "yes")
    else:
        coerced = value

    data[key] = coerced
    updated = GhostreaderConfig(**data)
    updated.save(project_dir)
    rprint(f"[green]Set[/green] {key} = {coerced}")


# ── Helpers ──────────────────────────────────────────────────────────


def _find_project_dir() -> Path | None:
    """Walk up from cwd looking for a directory containing config.yaml and .ghostreader/."""
    current = Path.cwd()
    for directory in [current, *current.parents]:
        if (directory / "config.yaml").exists() and (directory / ".ghostreader").is_dir():
            return directory
    return None
