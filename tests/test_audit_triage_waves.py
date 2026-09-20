"""Tests for audit-triage defer wave splitter."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_wave_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "audit-triage-split-defer-waves.py"
    spec = importlib.util.spec_from_file_location("audit_triage_split_defer_waves", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestWaveFor:
    def test_p0_is_wave_1(self) -> None:
        mod = _load_wave_module()
        assert mod.wave_for({"filePath": "ghostreader/x.py", "severity": "P0"}) == 1

    def test_p1_p2_still_wave_1(self) -> None:
        mod = _load_wave_module()
        assert mod.wave_for({"filePath": "ghostreader/x.py", "severity": "P1"}) == 1
        assert mod.wave_for({"filePath": "ghostreader/x.py", "severity": "P2"}) == 1
