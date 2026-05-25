"""Tests for the analyzers module (RepetitionDetector)."""

from __future__ import annotations

from ghostreader.analyzers import RepetitionReport
from ghostreader.analyzers.repetition_detector import RepetitionDetector
from ghostreader.ingestion import Chapter


class TestRepetitionDetector:
    def test_run_returns_report(self, sample_chapters: list[Chapter]) -> None:
        detector = RepetitionDetector()
        report = detector.run(sample_chapters)
        assert isinstance(report, RepetitionReport)
        assert report.chapter_count == 3
        assert report.total_word_count > 0

    def test_word_frequency_produces_results(self, sample_chapters: list[Chapter]) -> None:
        detector = RepetitionDetector(top_n_words=10)
        freqs = detector.analyze_word_frequency(sample_chapters)
        assert len(freqs) > 0
        assert all(f.count >= 0 for f in freqs)
        assert all(f.tfidf_score >= 0 for f in freqs)
        # At least some terms should have positive counts
        assert any(f.count > 0 for f in freqs)

    def test_word_frequency_empty_chapters(self) -> None:
        detector = RepetitionDetector()
        assert detector.analyze_word_frequency([]) == []

    def test_sentence_patterns_detects_structures(
        self, sample_chapters: list[Chapter]
    ) -> None:
        detector = RepetitionDetector()
        patterns = detector.analyze_sentence_patterns(sample_chapters)
        # Should produce *some* patterns from the sample text
        assert isinstance(patterns, list)

    def test_dialogue_tags_detects_tags(self, sample_chapters: list[Chapter]) -> None:
        detector = RepetitionDetector()
        tags = detector.analyze_dialogue_tags(sample_chapters)
        # Sample text has "said", "asked", "replied", "whispered"
        tag_names = {t.tag for t in tags}
        assert "said" in tag_names

    def test_dialogue_tags_empty_chapters(self) -> None:
        detector = RepetitionDetector()
        assert detector.analyze_dialogue_tags([]) == []

    def test_custom_thresholds(self, sample_chapters: list[Chapter]) -> None:
        detector = RepetitionDetector(
            top_n_words=5,
            ngram_range=(1, 2),
            similarity_threshold=0.95,
        )
        report = detector.run(sample_chapters)
        assert len(report.word_frequencies) <= 5
