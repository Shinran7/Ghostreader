"""Chat stack is optional (#20): lazy imports and the install hint."""

from __future__ import annotations

import subprocess
import sys

import pytest

from ghostreader.lancedb_util import CHAT_EXTRA_HINT, require_lancedb


def test_companion_import_skips_chat_stack() -> None:
    code = (
        "import sys\n"
        "import ghostreader.cli, ghostreader.commands.companion\n"
        "import ghostreader.companion.pipeline, ghostreader.ingestion.indexer\n"
        "bad = [m for m in ('lancedb', 'sentence_transformers', 'torch') if m in sys.modules]\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_commands_package_still_exports() -> None:
    import ghostreader.commands as commands

    assert callable(commands.run_compare)
    with pytest.raises(AttributeError):
        _ = commands.nope


def test_require_lancedb_missing_gives_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "lancedb", None)
    with pytest.raises(SystemExit) as exc:
        require_lancedb()
    assert exc.value.code == CHAT_EXTRA_HINT
