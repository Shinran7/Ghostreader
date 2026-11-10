"""Commands — chat and compare CLI subcommands.

Loaded lazily, so importing a sibling such as ``commands.companion`` does not
pull in the chat stack (LanceDB, an optional extra).
"""

from __future__ import annotations

from typing import Any

__all__ = ["run_chat", "run_compare"]


def __getattr__(name: str) -> Any:
    if name == "run_chat":
        from ghostreader.commands.chat import run_chat

        return run_chat
    if name == "run_compare":
        from ghostreader.commands.compare import run_compare

        return run_compare
    raise AttributeError(name)
