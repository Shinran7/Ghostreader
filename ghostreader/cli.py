"""Ghostreader CLI — AI literary analysis tool for fiction manuscripts."""

from __future__ import annotations

import asyncio
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
    asyncio.run(_run_ingestion(path, model=model))


async def _run_ingestion(path: Path, *, model: str | None = None) -> None:
    """Execute the ingestion pipeline: load → summarize → index."""
    from ghostreader.ingestion.epub_loader import load_epub
    from ghostreader.ingestion.indexer import index_manuscript
    from ghostreader.ingestion.markdown_loader import load_markdown
    from ghostreader.ingestion.summarizer import build_summary_hierarchy

    path = path.resolve()

    # ── Load chapters ──
    rprint(f"[cyan]Loading manuscript from:[/cyan] {path}")
    if path.is_file() and path.suffix.lower() == ".epub":
        chapters = load_epub(path)
    else:
        chapters = load_markdown(path)

    rprint(f"  Found [green]{len(chapters)}[/green] chapter(s)")

    # ── Build summary hierarchy ──
    rprint("[cyan]Building summary hierarchy...[/cyan]")
    llm = _get_llm(model)
    hierarchy = await build_summary_hierarchy(chapters, llm)
    rprint(
        f"  Summaries: [green]{len(hierarchy.chapter_summaries)}[/green] chapter, "
        f"[green]{len(hierarchy.act_summaries)}[/green] act, "
        f"[green]1[/green] global"
    )

    # ── Index into LanceDB ──
    project_dir = path.parent if path.is_file() else path
    rprint("[cyan]Indexing into LanceDB...[/cyan]")
    chunk_count, db_path = index_manuscript(chapters, hierarchy, project_dir)
    rprint(f"  Indexed [green]{chunk_count}[/green] chunks → {db_path}")

    # ── Summary panel ──
    table = Table(title="Ingestion Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Chapters", str(len(chapters)))
    table.add_row("Chunks", str(chunk_count))
    table.add_row("Chapter summaries", str(len(hierarchy.chapter_summaries)))
    table.add_row("Act summaries", str(len(hierarchy.act_summaries)))
    table.add_row("Global summary", "yes" if hierarchy.global_summary else "no")
    table.add_row("Database", str(db_path))
    rprint(table)
    rprint("[yellow]Analysis agents not yet implemented — ingestion complete.[/yellow]")


def _get_llm(model: str | None = None) -> "BaseChatModel":  # noqa: F821
    """Create a langchain ChatModel from config or --model override.

    Falls back to a FakeChatModel for testing when no real backend is
    configured or available.
    """
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, BaseMessage

    model_name = model or "stub"

    # Try real backends when a model name looks like a known provider
    if model_name.startswith("gpt-") or model_name.startswith("o"):
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model_name)
        except Exception:
            pass
    elif model_name.startswith("claude-"):
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=model_name)
        except Exception:
            pass

    # Stub model for pipeline testing without API keys
    class _StubChatModel(BaseChatModel):
        """Returns placeholder summaries so the pipeline runs end-to-end."""

        @property
        def _llm_type(self) -> str:
            return "stub"

        def _generate(
            self, messages: list[BaseMessage], **kwargs: object
        ) -> object:
            from langchain_core.outputs import ChatGeneration, ChatResult
            text = f"[stub summary of {len(messages[-1].content)} chars]"
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

        async def _agenerate(
            self, messages: list[BaseMessage], **kwargs: object
        ) -> object:
            return self._generate(messages, **kwargs)

    return _StubChatModel()


@app.command()
def chat(
    project: Annotated[str, typer.Argument(help="Project name to chat about.")],
    model: ModelOption = None,
) -> None:
    """Interactive follow-up chat with a previous analysis."""
    from ghostreader.commands.chat import run_chat

    project_dir = Path.cwd() / project
    if not (project_dir / ".ghostreader").is_dir():
        rprint(f"[red]Error:[/red] No Ghostreader project found at '{project_dir}'.")
        raise typer.Exit(code=1)

    run_chat(project_dir, model=model)


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
    from ghostreader.commands.compare import run_compare

    run_compare(
        path1,
        path2,
        output_format=format or "markdown",
        no_cache=no_cache,
    )


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
