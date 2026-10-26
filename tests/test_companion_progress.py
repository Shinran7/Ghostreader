"""Tests for progress cursor and order/gap warnings."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from ghostreader.companion.progress import (
    ProgressState,
    clamp_progress_to_disk,
    compute_order_warnings,
    load_progress,
    progress_path,
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

    def test_missing_later_files_preserve_high_water(self, tmp_path: Path) -> None:
        """Partial/renamed chapter dir must not permanently lower saved high-water."""
        save_progress(
            tmp_path,
            ProgressState(last_chapter_companioned=5, last_mode="progressive"),
        )
        max_on_disk = 3
        progress = clamp_progress_to_disk(tmp_path, max_on_disk)
        assert progress.last_chapter_companioned == 5
        assert load_progress(tmp_path).last_chapter_companioned == 5

        updated = update_progress_after_run(
            tmp_path,
            mode="progressive",
            chapter_number=3,
            gaps=[],
            max_chapter_on_disk=max_on_disk,
        )
        assert updated.last_chapter_companioned == 5
        assert load_progress(tmp_path).last_chapter_companioned == 5

    def test_partial_disk_still_warns_against_true_high_water(
        self, tmp_path: Path
    ) -> None:
        """Regression warnings use saved high-water, not a disk-clamped value."""
        save_progress(
            tmp_path,
            ProgressState(last_chapter_companioned=5, last_mode="progressive"),
        )
        max_on_disk = 3
        progress = clamp_progress_to_disk(tmp_path, max_on_disk)
        warnings = compute_order_warnings(
            mode="progressive",
            chapter_number=3,
            gaps=[],
            progress=progress,
            max_chapter_on_disk=max_on_disk,
        )
        assert any("Regression" in w for w in warnings)
        assert any("chapter 5" in w for w in warnings)

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

    def test_files_return_keeps_high_water_no_reprocess_cursor(
        self, tmp_path: Path
    ) -> None:
        """After a partial-dir run, restored files still see the original high-water."""
        save_progress(
            tmp_path,
            ProgressState(last_chapter_companioned=5, last_mode="progressive"),
        )
        update_progress_after_run(
            tmp_path,
            mode="progressive",
            chapter_number=3,
            gaps=[],
            max_chapter_on_disk=3,
        )
        # Files "return" — disk max back to 5; cursor must still be 5.
        progress = clamp_progress_to_disk(tmp_path, 5)
        assert progress.last_chapter_companioned == 5
        warnings = compute_order_warnings(
            mode="progressive",
            chapter_number=5,
            gaps=[],
            progress=progress,
            max_chapter_on_disk=5,
        )
        assert not any("Skip/gap" in w for w in warnings)

    def test_concurrent_updates_preserve_high_water(self, tmp_path: Path) -> None:
        """Locked RMW: overlapping progressive updates keep max chapter."""
        save_progress(
            tmp_path,
            ProgressState(last_chapter_companioned=1, last_mode="progressive"),
        )
        errors: list[BaseException] = []
        barrier = threading.Barrier(2)

        def run_chapter(n: int) -> None:
            try:
                barrier.wait(timeout=5)
                update_progress_after_run(
                    tmp_path,
                    mode="progressive",
                    chapter_number=n,
                    gaps=[],
                )
            except BaseException as exc:  # noqa: BLE001 — collect for assert
                errors.append(exc)

        t_high = threading.Thread(target=run_chapter, args=(10,))
        t_low = threading.Thread(target=run_chapter, args=(8,))
        t_high.start()
        t_low.start()
        t_high.join(timeout=10)
        t_low.join(timeout=10)
        assert not errors
        assert load_progress(tmp_path).last_chapter_companioned == 10
        raw = json.loads(progress_path(tmp_path).read_text(encoding="utf-8"))
        assert raw["last_chapter_companioned"] == 10
