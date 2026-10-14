"""Tests for progress cursor and order/gap warnings."""

from __future__ import annotations

from pathlib import Path

from ghostreader.companion.progress import (
    ProgressState,
    clamp_progress_to_disk,
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

    def test_rewrite_later_gone_no_false_warning_and_clamps(self, tmp_path: Path) -> None:
        """Restore/truncate removed Ch4+; progress still says 5 → no phantom warn."""
        save_progress(
            tmp_path,
            ProgressState(last_chapter_companioned=5, last_mode="progressive"),
        )
        max_on_disk = 3
        progress = clamp_progress_to_disk(tmp_path, max_on_disk)
        assert progress.last_chapter_companioned == 3

        warnings = compute_order_warnings(
            mode="progressive",
            chapter_number=3,
            gaps=[],
            progress=progress,
            max_chapter_on_disk=max_on_disk,
        )
        assert not any("Regression" in w for w in warnings)

        updated = update_progress_after_run(
            tmp_path,
            mode="progressive",
            chapter_number=3,
            gaps=[],
            max_chapter_on_disk=max_on_disk,
        )
        assert updated.last_chapter_companioned == 3

    def test_rewrite_later_still_present_warns(self, tmp_path: Path) -> None:
        """Rewrite Ch3 while Ch4–5 still on disk → regression warning + high-water."""
        save_progress(
            tmp_path,
            ProgressState(last_chapter_companioned=5, last_mode="progressive"),
        )
        max_on_disk = 5
        progress = load_progress(tmp_path)
        warnings = compute_order_warnings(
            mode="progressive",
            chapter_number=3,
            gaps=[],
            progress=progress,
            max_chapter_on_disk=max_on_disk,
        )
        assert any("Regression" in w for w in warnings)

        updated = update_progress_after_run(
            tmp_path,
            mode="progressive",
            chapter_number=3,
            gaps=[],
            max_chapter_on_disk=max_on_disk,
        )
        assert updated.last_chapter_companioned == 5
