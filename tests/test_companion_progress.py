"""Tests for progress cursor and order/gap warnings."""

from __future__ import annotations

from pathlib import Path

from ghostreader.companion.progress import (
    ProgressState,
    compute_order_warnings,
    load_progress,
    save_progress,
    update_progress_after_run,
)


class TestProgressCursor:
    def test_regression_warning(self, tmp_path: Path) -> None:
        save_progress(
            tmp_path,
            ProgressState(last_chapter_companioned=18, last_mode="progressive"),
        )
        progress = load_progress(tmp_path)
        warnings = compute_order_warnings(
            mode="progressive",
            chapter_number=12,
            gaps=[],
            progress=progress,
        )
        assert any("Regression" in w for w in warnings)

    def test_skip_warning(self, tmp_path: Path) -> None:
        progress = ProgressState(last_chapter_companioned=5, last_mode="progressive")
        warnings = compute_order_warnings(
            mode="progressive",
            chapter_number=8,
            gaps=[],
            progress=progress,
        )
        assert any("Skip/gap" in w for w in warnings)
        assert "6" in warnings[0] or "7" in warnings[0]

    def test_rewrite_does_not_lower_cursor(self, tmp_path: Path) -> None:
        save_progress(
            tmp_path,
            ProgressState(last_chapter_companioned=18, last_mode="progressive"),
        )
        updated = update_progress_after_run(
            tmp_path,
            mode="progressive",
            chapter_number=12,
            gaps=[],
        )
        assert updated.last_chapter_companioned == 18

    def test_progressive_advances_cursor(self, tmp_path: Path) -> None:
        updated = update_progress_after_run(
            tmp_path,
            mode="progressive",
            chapter_number=3,
            gaps=[],
        )
        assert updated.last_chapter_companioned == 3
        again = update_progress_after_run(
            tmp_path,
            mode="progressive",
            chapter_number=4,
            gaps=[],
        )
        assert again.last_chapter_companioned == 4
