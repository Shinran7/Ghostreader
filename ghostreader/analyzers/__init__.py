"""Analyzers — algorithmic pre-processing for manuscript analysis."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WordFrequency:
    """A single overused word or phrase detected via tf-idf analysis."""

    term: str
    count: int
    tfidf_score: float
    locations: list[TermLocation] = field(default_factory=list)


@dataclass
class TermLocation:
    """Where a term appears in the manuscript."""

    chapter_number: int
    chapter_title: str
    approximate_position: float  # 0.0–1.0 within the chapter


@dataclass
class RepeatedPhrase:
    """A phrase (2+ words) that recurs across or within chapters."""

    phrase: str
    count: int
    locations: list[TermLocation] = field(default_factory=list)


@dataclass
class SentencePattern:
    """A detected structural pattern in sentence construction."""

    pattern_type: str  # "repeated_opening", "similar_structure", "length_monotony"
    description: str
    examples: list[str]
    chapter_number: int
    similarity_score: float  # 0.0–1.0 for fuzzy matches


@dataclass
class DialogueTagStats:
    """Aggregated statistics about dialogue tag usage."""

    tag: str  # e.g. "said", "whispered"
    count: int
    is_adverb_heavy: bool
    adverbs: list[str] = field(default_factory=list)
    chapter_counts: dict[int, int] = field(default_factory=dict)


@dataclass
class RepetitionReport:
    """Combined output of all repetition detection analyses."""

    word_frequencies: list[WordFrequency] = field(default_factory=list)
    repeated_phrases: list[RepeatedPhrase] = field(default_factory=list)
    sentence_patterns: list[SentencePattern] = field(default_factory=list)
    dialogue_tags: list[DialogueTagStats] = field(default_factory=list)
    chapter_count: int = 0
    total_word_count: int = 0


__all__ = [
    "DialogueTagStats",
    "RepeatedPhrase",
    "RepetitionReport",
    "SentencePattern",
    "TermLocation",
    "WordFrequency",
]
