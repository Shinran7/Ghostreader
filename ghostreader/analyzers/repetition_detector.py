"""Algorithmic repetition detection — tf-idf word frequency, fuzzy sentence
pattern matching, and dialogue tag analysis.

All detection is purely algorithmic (no LLM calls). Results are structured data
intended for consumption by the Prose Analyst agent.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from sklearn.feature_extraction.text import TfidfVectorizer

from ghostreader.analyzers import (
    DialogueTagStats,
    RepeatedPhrase,
    RepetitionReport,
    SentencePattern,
    TermLocation,
    WordFrequency,
)

if TYPE_CHECKING:
    from ghostreader.ingestion import Chapter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Common English stop-words that should never surface as "overused".
_EXTRA_STOP_WORDS = frozenset(
    {
        "a", "an", "the", "and", "but", "or", "is", "was", "were", "are",
        "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "shall", "should", "may", "might", "must", "can",
        "could", "to", "of", "in", "for", "on", "with", "at", "by", "from",
        "as", "into", "through", "during", "before", "after", "above", "below",
        "between", "out", "off", "over", "under", "again", "further", "then",
        "once", "here", "there", "when", "where", "why", "how", "all", "each",
        "every", "both", "few", "more", "most", "other", "some", "such", "no",
        "nor", "not", "only", "own", "same", "so", "than", "too", "very",
        "just", "because", "about", "up", "it", "its", "he", "she", "they",
        "them", "his", "her", "their", "him", "my", "your", "we", "me", "i",
        "you", "that", "this", "those", "these", "what", "which", "who",
        "whom", "if", "while", "until", "also", "still", "even", "back",
        "much", "many", "well", "like", "now", "one", "two", "get", "got",
        "make", "made", "go", "went", "come", "came", "see", "saw", "know",
        "knew", "take", "took", "think", "thought", "say", "said", "tell",
        "told", "give", "gave", "look", "looked", "find", "found", "want",
        "let", "seem", "seemed", "yes", "no", "oh", "okay", "right", "left",
        "thing", "things", "way", "time", "day", "man", "woman", "don",
        "didn", "doesn", "won", "wouldn", "couldn", "shouldn", "isn", "wasn",
        "weren", "aren", "hadn", "hasn", "haven", "ll", "ve", "re", "it's",
    }
)

# Dialogue tag verb lemma -> canonical form mapping.
_DIALOGUE_VERBS: dict[str, str] = {
    "said": "said", "says": "said", "say": "said", "saying": "said",
    "asked": "asked", "ask": "asked", "asks": "asked", "asking": "asked",
    "whispered": "whispered", "whisper": "whispered", "whispers": "whispered",
    "shouted": "shouted", "shout": "shouted", "shouts": "shouted",
    "yelled": "yelled", "yell": "yelled", "yells": "yelled",
    "exclaimed": "exclaimed", "exclaim": "exclaimed", "exclaims": "exclaimed",
    "muttered": "muttered", "mutter": "muttered", "mutters": "muttered",
    "murmured": "murmured", "murmur": "murmured", "murmurs": "murmured",
    "replied": "replied", "reply": "replied", "replies": "replied",
    "answered": "answered", "answer": "answered", "answers": "answered",
    "called": "called", "call": "called", "calls": "called",
    "cried": "cried", "cry": "cried", "cries": "cried",
    "declared": "declared", "declare": "declared", "declares": "declared",
    "demanded": "demanded", "demand": "demanded", "demands": "demanded",
    "gasped": "gasped", "gasp": "gasped", "gasps": "gasped",
    "groaned": "groaned", "groan": "groaned", "groans": "groaned",
    "growled": "growled", "growl": "growled", "growls": "growled",
    "hissed": "hissed", "hiss": "hissed", "hisses": "hissed",
    "insisted": "insisted", "insist": "insisted", "insists": "insisted",
    "laughed": "laughed", "laugh": "laughed", "laughs": "laughed",
    "moaned": "moaned", "moan": "moaned", "moans": "moaned",
    "pleaded": "pleaded", "plead": "pleaded", "pleads": "pleaded",
    "promised": "promised", "promise": "promised", "promises": "promised",
    "protested": "protested", "protest": "protested", "protests": "protested",
    "screamed": "screamed", "scream": "screamed", "screams": "screamed",
    "sighed": "sighed", "sigh": "sighed", "sighs": "sighed",
    "snapped": "snapped", "snap": "snapped", "snaps": "snapped",
    "sobbed": "sobbed", "sob": "sobbed", "sobs": "sobbed",
    "stammered": "stammered", "stammer": "stammered", "stammers": "stammered",
    "stuttered": "stuttered", "stutter": "stuttered", "stutters": "stuttered",
    "suggested": "suggested", "suggest": "suggested", "suggests": "suggested",
    "warned": "warned", "warn": "warned", "warns": "warned",
    "wailed": "wailed", "wail": "wailed", "wails": "wailed",
    "wondered": "wondered", "wonder": "wondered", "wonders": "wondered",
    "admitted": "admitted", "admit": "admitted", "admits": "admitted",
    "agreed": "agreed", "agree": "agreed", "agrees": "agreed",
    "announced": "announced", "announce": "announced", "announces": "announced",
    "barked": "barked", "bark": "barked", "barks": "barked",
    "begged": "begged", "beg": "begged", "begs": "begged",
    "bellowed": "bellowed", "bellow": "bellowed", "bellows": "bellowed",
    "breathed": "breathed", "breathe": "breathed", "breathes": "breathed",
    "chuckled": "chuckled", "chuckle": "chuckled", "chuckles": "chuckled",
    "commented": "commented", "comment": "commented", "comments": "commented",
    "confessed": "confessed", "confess": "confessed", "confesses": "confessed",
    "continued": "continued", "continue": "continued", "continues": "continued",
    "corrected": "corrected", "correct": "corrected", "corrects": "corrected",
    "grumbled": "grumbled", "grumble": "grumbled", "grumbles": "grumbled",
    "interrupted": "interrupted", "interrupt": "interrupted",
    "lied": "lied", "lie": "lied", "lies": "lied",
    "mentioned": "mentioned", "mention": "mentioned", "mentions": "mentioned",
    "mumbled": "mumbled", "mumble": "mumbled", "mumbles": "mumbled",
    "noted": "noted", "note": "noted", "notes": "noted",
    "observed": "observed", "observe": "observed", "observes": "observed",
    "offered": "offered", "offer": "offered", "offers": "offered",
    "ordered": "ordered", "order": "ordered", "orders": "ordered",
    "repeated": "repeated", "repeat": "repeated", "repeats": "repeated",
    "responded": "responded", "respond": "responded", "responds": "responded",
    "retorted": "retorted", "retort": "retorted", "retorts": "retorted",
    "roared": "roared", "roar": "roared", "roars": "roared",
    "shrieked": "shrieked", "shriek": "shrieked", "shrieks": "shrieked",
    "sneered": "sneered", "sneer": "sneered", "sneers": "sneered",
    "spoke": "spoke", "speak": "spoke", "speaks": "spoke",
    "urged": "urged", "urge": "urged", "urges": "urged",
    "whimpered": "whimpered", "whimper": "whimpered", "whimpers": "whimpered",
    "whined": "whined", "whine": "whined", "whines": "whined",
}

# Regex for dialogue attribution: closing quote, optional comma, then tag.
_DIALOGUE_TAG_RE = re.compile(
    r'["\u201c\u201d\u2018\u2019\']\s*'       # closing quotation mark
    r"[,.]?\s+"                                 # optional comma/period + space
    r"(?:(?:he|she|they|[A-Z][a-z]+)\s+)?"     # optional subject
    r"(\w+)"                                    # the verb (capture group 1)
    r"(\s+\w+ly)?"                              # optional adverb (capture group 2)
)

# Minimum similarity threshold for fuzzy sentence matching.
_SIMILARITY_THRESHOLD = 0.70

# How many words constitute a "sentence opening" for repeated-opening detection.
_OPENING_WORD_COUNT = 3

# Minimum occurrences before a sentence opening is flagged.
_OPENING_MIN_COUNT = 3

# Number of consecutive sentences with similar length to flag monotony.
_LENGTH_MONOTONY_WINDOW = 5
_LENGTH_MONOTONY_TOLERANCE = 0.20  # within 20% of mean length


class RepetitionDetector:
    """Purely algorithmic repetition detection for fiction manuscripts.

    Uses scikit-learn ``TfidfVectorizer`` for word/phrase frequency analysis
    and stdlib ``difflib.SequenceMatcher`` for fuzzy sentence matching.
    No LLM calls are made.
    """

    def __init__(
        self,
        *,
        top_n_words: int = 50,
        ngram_range: tuple[int, int] = (1, 3),
        similarity_threshold: float = _SIMILARITY_THRESHOLD,
        opening_word_count: int = _OPENING_WORD_COUNT,
    ) -> None:
        self.top_n_words = top_n_words
        self.ngram_range = ngram_range
        self.similarity_threshold = similarity_threshold
        self.opening_word_count = opening_word_count

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, chapters: list[Chapter]) -> RepetitionReport:
        """Orchestrate all analyses and return a combined report."""
        total_words = sum(len(ch.content.split()) for ch in chapters)
        return RepetitionReport(
            word_frequencies=self.analyze_word_frequency(chapters),
            repeated_phrases=self._analyze_phrase_frequency(chapters),
            sentence_patterns=self.analyze_sentence_patterns(chapters),
            dialogue_tags=self.analyze_dialogue_tags(chapters),
            chapter_count=len(chapters),
            total_word_count=total_words,
        )

    # ------------------------------------------------------------------
    # Word / phrase frequency (tf-idf)
    # ------------------------------------------------------------------

    def analyze_word_frequency(
        self, chapters: list[Chapter],
    ) -> list[WordFrequency]:
        """Detect overused *single* words via tf-idf across chapters.

        Returns a ranked list (highest tf-idf score first) capped at
        ``self.top_n_words``.
        """
        if not chapters:
            return []

        docs = [ch.content for ch in chapters]
        vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 1),
            max_features=5000,
            token_pattern=r"(?u)\b[a-zA-Z]{2,}\b",
        )
        tfidf_matrix = vectorizer.fit_transform(docs)
        feature_names = vectorizer.get_feature_names_out()

        # Aggregate tf-idf across chapters (mean score).
        mean_scores: dict[str, float] = {}
        for idx, term in enumerate(feature_names):
            col = tfidf_matrix.getcol(idx).toarray().flatten()
            score = float(col.mean())
            if term.lower() not in _EXTRA_STOP_WORDS:
                mean_scores[term] = score

        # Sort descending by score, take top N.
        ranked = sorted(mean_scores.items(), key=lambda x: x[1], reverse=True)
        ranked = ranked[: self.top_n_words]

        results: list[WordFrequency] = []
        for term, score in ranked:
            locations = self._locate_term(term, chapters)
            total_count = sum(
                ch.content.lower().split().count(term.lower()) for ch in chapters
            )
            results.append(
                WordFrequency(
                    term=term,
                    count=total_count,
                    tfidf_score=round(score, 4),
                    locations=locations,
                ),
            )
        return results

    def _analyze_phrase_frequency(
        self, chapters: list[Chapter],
    ) -> list[RepeatedPhrase]:
        """Detect overused multi-word phrases (bigrams/trigrams) via tf-idf."""
        if not chapters:
            return []

        docs = [ch.content for ch in chapters]
        vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(2, self.ngram_range[1]),
            max_features=5000,
            token_pattern=r"(?u)\b[a-zA-Z]{2,}\b",
        )
        tfidf_matrix = vectorizer.fit_transform(docs)
        feature_names = vectorizer.get_feature_names_out()

        # Raw count across all chapters for each n-gram.
        phrase_counts: Counter[str] = Counter()
        for ch in chapters:
            text_lower = ch.content.lower()
            for phrase in feature_names:
                c = text_lower.count(phrase.lower())
                if c > 0:
                    phrase_counts[phrase] += c

        # Keep only phrases appearing 3+ times.
        repeated = {p: c for p, c in phrase_counts.items() if c >= 3}
        if not repeated:
            return []

        # Score = raw count * mean tf-idf (rewards both frequency and salience).
        scored: list[tuple[str, int, float]] = []
        for phrase, count in repeated.items():
            idx = list(feature_names).index(phrase)
            col = tfidf_matrix.getcol(idx).toarray().flatten()
            tfidf_mean = float(col.mean())
            scored.append((phrase, count, count * tfidf_mean))

        scored.sort(key=lambda x: x[2], reverse=True)
        scored = scored[: self.top_n_words]

        results: list[RepeatedPhrase] = []
        for phrase, count, _ in scored:
            locations = self._locate_term(phrase, chapters)
            results.append(
                RepeatedPhrase(phrase=phrase, count=count, locations=locations),
            )
        return results

    # ------------------------------------------------------------------
    # Sentence structure patterns
    # ------------------------------------------------------------------

    def analyze_sentence_patterns(
        self, chapters: list[Chapter],
    ) -> list[SentencePattern]:
        """Detect structural repetition: repeated openings, similar structures,
        and length monotony.
        """
        patterns: list[SentencePattern] = []
        for ch in chapters:
            sentences = _split_sentences(ch.content)
            if len(sentences) < 2:
                continue

            patterns.extend(self._detect_repeated_openings(sentences, ch))
            patterns.extend(self._detect_similar_structures(sentences, ch))
            patterns.extend(self._detect_length_monotony(sentences, ch))
        return patterns

    def _detect_repeated_openings(
        self,
        sentences: list[str],
        chapter: Chapter,
    ) -> list[SentencePattern]:
        """Flag sentence openings that recur >= _OPENING_MIN_COUNT times."""
        openings: dict[str, list[str]] = defaultdict(list)
        for sent in sentences:
            words = sent.split()
            if len(words) >= self.opening_word_count:
                key = " ".join(words[: self.opening_word_count]).lower()
                openings[key].append(sent)

        results: list[SentencePattern] = []
        for opening, examples in openings.items():
            if len(examples) >= _OPENING_MIN_COUNT:
                results.append(
                    SentencePattern(
                        pattern_type="repeated_opening",
                        description=(
                            f'Opening "{opening}" appears {len(examples)} times'
                        ),
                        examples=examples[:5],
                        chapter_number=chapter.chapter_number,
                        similarity_score=1.0,
                    ),
                )
        return results

    def _detect_similar_structures(
        self,
        sentences: list[str],
        chapter: Chapter,
    ) -> list[SentencePattern]:
        """Use fuzzy matching to find near-duplicate sentence constructions."""
        results: list[SentencePattern] = []
        seen_pairs: set[tuple[int, int]] = set()

        for i, sent_a in enumerate(sentences):
            if len(sent_a.split()) < 4:
                continue
            for j in range(i + 1, min(i + 20, len(sentences))):
                if (i, j) in seen_pairs:
                    continue
                sent_b = sentences[j]
                if len(sent_b.split()) < 4:
                    continue

                ratio = SequenceMatcher(
                    None, sent_a.lower(), sent_b.lower(),
                ).ratio()
                if ratio >= self.similarity_threshold:
                    seen_pairs.add((i, j))
                    results.append(
                        SentencePattern(
                            pattern_type="similar_structure",
                            description=(
                                f"Near-duplicate sentences "
                                f"(similarity {ratio:.0%})"
                            ),
                            examples=[sent_a.strip(), sent_b.strip()],
                            chapter_number=chapter.chapter_number,
                            similarity_score=round(ratio, 3),
                        ),
                    )
        return results

    def _detect_length_monotony(
        self,
        sentences: list[str],
        chapter: Chapter,
    ) -> list[SentencePattern]:
        """Flag runs of consecutive sentences with very similar word counts."""
        results: list[SentencePattern] = []
        lengths = [len(s.split()) for s in sentences]

        for start in range(len(lengths) - _LENGTH_MONOTONY_WINDOW + 1):
            window = lengths[start : start + _LENGTH_MONOTONY_WINDOW]
            mean_len = sum(window) / len(window)
            if mean_len < 3:
                continue
            if all(
                abs(wl - mean_len) / mean_len <= _LENGTH_MONOTONY_TOLERANCE
                for wl in window
            ):
                examples = sentences[start : start + _LENGTH_MONOTONY_WINDOW]
                results.append(
                    SentencePattern(
                        pattern_type="length_monotony",
                        description=(
                            f"{_LENGTH_MONOTONY_WINDOW} consecutive sentences "
                            f"averaging ~{mean_len:.0f} words each"
                        ),
                        examples=[s.strip() for s in examples[:3]],
                        chapter_number=chapter.chapter_number,
                        similarity_score=round(
                            1.0 - max(
                                abs(wl - mean_len) / mean_len for wl in window
                            ),
                            3,
                        ),
                    ),
                )
        return results

    # ------------------------------------------------------------------
    # Dialogue tag analysis
    # ------------------------------------------------------------------

    def analyze_dialogue_tags(
        self, chapters: list[Chapter],
    ) -> list[DialogueTagStats]:
        """Count and categorize dialogue attribution tags across the manuscript.

        Detects adverb-heavy tags and per-chapter distributions.
        """
        tag_counter: Counter[str] = Counter()
        tag_adverbs: dict[str, Counter[str]] = defaultdict(Counter)
        tag_chapter_counts: dict[str, Counter[int]] = defaultdict(Counter)

        for ch in chapters:
            for match in _DIALOGUE_TAG_RE.finditer(ch.content):
                verb_raw = match.group(1).lower()
                adverb_raw = match.group(2)

                canonical = _DIALOGUE_VERBS.get(verb_raw)
                if canonical is None:
                    continue

                tag_counter[canonical] += 1
                tag_chapter_counts[canonical][ch.chapter_number] += 1

                if adverb_raw:
                    tag_adverbs[canonical][adverb_raw.strip().lower()] += 1

        results: list[DialogueTagStats] = []
        for tag, count in tag_counter.most_common():
            adverb_total = sum(tag_adverbs[tag].values())
            results.append(
                DialogueTagStats(
                    tag=tag,
                    count=count,
                    is_adverb_heavy=adverb_total > count * 0.3,
                    adverbs=[
                        adv for adv, _ in tag_adverbs[tag].most_common(10)
                    ],
                    chapter_counts=dict(tag_chapter_counts[tag]),
                ),
            )
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _locate_term(
        term: str, chapters: list[Chapter],
    ) -> list[TermLocation]:
        """Find approximate positions of *term* across all chapters."""
        locations: list[TermLocation] = []
        term_lower = term.lower()
        for ch in chapters:
            text_lower = ch.content.lower()
            idx = 0
            while True:
                pos = text_lower.find(term_lower, idx)
                if pos == -1:
                    break
                approx = pos / max(len(text_lower), 1)
                locations.append(
                    TermLocation(
                        chapter_number=ch.chapter_number,
                        chapter_title=ch.title,
                        approximate_position=round(approx, 3),
                    ),
                )
                idx = pos + len(term_lower)
        return locations


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    """Rough sentence splitter suitable for fiction prose.

    Splits on period, exclamation, or question mark followed by whitespace
    or end-of-string, while avoiding false splits on common abbreviations
    (Mr., Mrs., Dr., etc.).
    """
    # Protect common abbreviations.
    protected = text
    for abbr in ("Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sr.", "Jr.", "St."):
        protected = protected.replace(abbr, abbr.replace(".", "\x00"))

    parts = re.split(r'(?<=[.!?])\s+', protected)
    return [p.replace("\x00", ".").strip() for p in parts if p.strip()]
