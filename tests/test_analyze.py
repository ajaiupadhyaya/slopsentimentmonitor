"""Sentiment tests.

Deliberately biased toward developer vocabulary, because that is where
off-the-shelf lexicons fail and where all of our documents come from.
"""

from __future__ import annotations

import pytest

from pulseai.config import Settings
from pulseai.pipeline.analyze import (
    HeuristicAnalyzer,
    SentimentScore,
    aspect_text,
    get_analyzer,
)


@pytest.fixture(scope="module")
def analyzer() -> HeuristicAnalyzer:
    return HeuristicAnalyzer()


@pytest.mark.parametrize(
    "text",
    [
        "This model is absolutely fantastic for refactoring",
        "Honestly the best coding assistant I've used",
        "Fast, accurate, and cheap. Highly recommend it.",
        "Rock solid so far, zero complaints",
        "stupid fast compared to the old one",
    ],
)
def test_clear_praise_scores_positive(analyzer: HeuristicAnalyzer, text: str) -> None:
    assert analyzer.score(text).compound > 0


@pytest.mark.parametrize(
    "text",
    [
        "Completely broken since the last update, unusable",
        "It hallucinates constantly and the rate limits are awful",
        "Slow, overpriced, and the API keeps erroring out",
        "Deeply disappointing regression, they nerfed it",
        "I cancelled my subscription, total waste of money",
    ],
)
def test_clear_complaints_score_negative(analyzer: HeuristicAnalyzer, text: str) -> None:
    assert analyzer.score(text).compound < 0


def test_developer_slang_is_not_read_literally(analyzer: HeuristicAnalyzer) -> None:
    """The failure mode that rules out general-purpose lexicons."""
    assert analyzer.score("this thing is insane at debugging").compound > 0
    assert analyzer.score("the autocomplete is sick").compound > 0
    assert analyzer.score("stupid fast inference").compound > 0


def test_negation_flips_polarity(analyzer: HeuristicAnalyzer) -> None:
    assert analyzer.score("this is good").compound > 0
    assert analyzer.score("this is not good").compound < 0
    assert analyzer.score("it doesn't crash anymore").compound > 0


def test_negation_is_weaker_than_direct_statement(analyzer: HeuristicAnalyzer) -> None:
    """"not great" is lukewarm, not the mirror image of "great"."""
    direct = abs(analyzer.score("terrible").compound)
    negated = abs(analyzer.score("not great").compound)
    assert negated < direct


def test_intensifiers_amplify(analyzer: HeuristicAnalyzer) -> None:
    mild = analyzer.score("it is good")
    strong = analyzer.score("it is extremely good")
    assert strong.compound > mild.compound


def test_neutral_text_is_neutral(analyzer: HeuristicAnalyzer) -> None:
    score = analyzer.score("The API returns JSON with a list of model identifiers.")
    assert score.compound == 0.0
    assert score.neutral == 1.0
    assert score.confidence == 0.0


def test_empty_input_is_safe(analyzer: HeuristicAnalyzer) -> None:
    for value in ("", "   ", "\n\t"):
        score = analyzer.score(value)
        assert score.compound == 0.0
        assert score.confidence == 0.0


def test_sparse_signal_yields_low_confidence(analyzer: HeuristicAnalyzer) -> None:
    """One adjective buried in an essay should not read as a confident verdict."""
    filler = "The request pipeline serialises payloads to the worker queue. " * 40
    sparse = analyzer.score(filler + " It is good.")
    dense = analyzer.score("Amazing, excellent, fantastic, love it, best ever, brilliant")
    assert sparse.confidence < dense.confidence


def test_scores_stay_in_range(analyzer: HeuristicAnalyzer) -> None:
    texts = [
        "amazing amazing amazing incredible best!!!",
        "garbage garbage terrible unusable worst!!!",
        "mixed bag: great speed but terrible pricing",
    ]
    for text in texts:
        score = analyzer.score(text)
        assert -1.0 <= score.compound <= 1.0
        assert 0.0 <= score.positive <= 1.0
        assert 0.0 <= score.negative <= 1.0
        assert 0.0 <= score.confidence <= 1.0


def test_mixed_sentiment_lands_between_the_extremes(analyzer: HeuristicAnalyzer) -> None:
    mixed = analyzer.score("great at coding but the pricing is terrible").compound
    assert abs(mixed) < abs(analyzer.score("great at coding").compound)


# ---------------------------------------------------------------------------
# Aspect windowing — the mechanism that makes comparison posts scoreable
# ---------------------------------------------------------------------------


def test_aspect_text_isolates_the_region_around_a_mention() -> None:
    text = "A" * 1000 + " CLAUDE " + "B" * 1000
    start = text.index("CLAUDE")
    window = aspect_text(text, [(start, start + 6)], window=20)
    assert "CLAUDE" in window
    assert len(window) < len(text)


def test_aspect_windows_merge_when_overlapping() -> None:
    text = "x Claude y Claude z"
    positions = [(2, 8), (11, 17)]
    merged = aspect_text(text, positions, window=50)
    assert merged.count("Claude") == 2


def test_aspect_text_returns_whole_text_without_positions() -> None:
    assert aspect_text("hello world", []) == "hello world"


def test_comparison_post_scores_each_model_separately(analyzer: HeuristicAnalyzer) -> None:
    """The reason sentiment is keyed per (document, model)."""
    text = (
        "Claude has been excellent for refactoring, genuinely impressive and reliable. "
        "Meanwhile Gemini keeps hallucinating and the errors are frustrating and useless."
    )
    claude_start = text.index("Claude")
    gemini_start = text.index("Gemini")

    claude = analyzer.score(aspect_text(text, [(claude_start, claude_start + 6)], window=60))
    gemini = analyzer.score(aspect_text(text, [(gemini_start, gemini_start + 6)], window=60))

    assert claude.compound > 0
    assert gemini.compound < 0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_heuristic_is_selected_explicitly() -> None:
    chosen = get_analyzer(Settings(analyzer="heuristic"))
    assert chosen.name == "heuristic"


def test_auto_never_raises() -> None:
    """`auto` must degrade to heuristic rather than block the pipeline."""
    assert get_analyzer(Settings(analyzer="auto")).name in {"local", "heuristic"}


def test_local_mode_fails_loudly_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicitly asking for `local` must not silently downgrade."""
    from pulseai.pipeline import analyze

    monkeypatch.setattr(analyze.LocalAnalyzer, "is_available", staticmethod(lambda: False))
    with pytest.raises(RuntimeError, match="uv sync --extra ml"):
        get_analyzer(Settings(analyzer="local"))


def test_sentiment_score_compound_is_derived() -> None:
    score = SentimentScore(positive=0.8, negative=0.1, neutral=0.1, confidence=0.9, analyzer="t")
    assert score.compound == pytest.approx(0.7)
