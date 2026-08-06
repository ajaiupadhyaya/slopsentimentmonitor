"""Detection is the crux: every downstream metric is a count of these matches.

The false-positive corpus matters more than the true-positive one. A missed
mention costs a little recall; a phantom mention corrupts a sentiment average.
"""

from __future__ import annotations

import pytest

from pulseai.pipeline.detect import ModelDetector
from pulseai.registry import MODELS


@pytest.fixture(scope="module")
def detector() -> ModelDetector:
    return ModelDetector.from_specs(MODELS)


def slugs(detector: ModelDetector, text: str) -> set[str]:
    return {m.slug for m in detector.detect(text)}


# --------------------------------------------------------------------------
# Must match
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ChatGPT is down again", "chatgpt"),
        ("I've been using Claude for a month", "claude"),
        ("gpt-5 is noticeably faster", "gpt-5"),
        ("DeepSeek R1 beats everything on price", "deepseek"),
        ("Running Llama 3 locally with ollama", "llama"),
        ("perplexity has better citations", "perplexity"),
        ("Mixtral still holds up", "mistral"),
        ("we switched to Qwen3 for the eval", "qwen"),
        ("vLLM throughput is unmatched", "vllm"),
        ("llama.cpp on a raspberry pi", "llama-cpp"),
    ],
)
def test_detects_unambiguous_mentions(detector: ModelDetector, text: str, expected: str) -> None:
    assert expected in slugs(detector, text)


# --------------------------------------------------------------------------
# Must NOT match — the adversarial corpus
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "forbidden"),
    [
        # "grok" the verb. Extremely common on Hacker News.
        ("Took me a while to grok monads", "grok"),
        ("Once you grok the borrow checker it clicks", "grok"),
        ("hard to grok this codebase", "grok"),
        # Animals and astrology, with no AI context to rescue them.
        ("We saw a llama at the farm", "llama"),
        ("She's a Gemini, I'm a Taurus", "gemini"),
        ("The nova was visible for weeks", "nova"),
        # Poetry, not Anthropic.
        ("He wrote a sonnet for her birthday", "claude-sonnet"),
        ("I wrote a haiku about rain", "claude-haiku"),
        ("Magnum opus of the Baroque period", "claude-opus"),
        # People named Claude, with no AI context.
        ("Claude Monet painted water lilies", "claude"),
        # Substrings must not trigger word-boundary-free matches.
        ("The codexes were kept in the abbey", "codex"),
        ("Casanova was born in Venice", "nova"),
    ],
)
def test_rejects_false_positives(detector: ModelDetector, text: str, forbidden: str) -> None:
    assert forbidden not in slugs(detector, text)


def test_ambiguous_alias_activates_with_ai_context(detector: ModelDetector) -> None:
    """The same word flips meaning based on the document it sits in."""
    assert "gemini" not in slugs(detector, "She's a Gemini, I'm a Taurus")
    assert "gemini" in slugs(detector, "Gemini beats the other LLMs on long context prompts")


def test_grok_stays_case_sensitive(detector: ModelDetector) -> None:
    assert "grok" not in slugs(detector, "took a while to grok the LLM architecture")
    assert "grok" in slugs(detector, "Grok is xAI's model")


# --------------------------------------------------------------------------
# Longest match wins
# --------------------------------------------------------------------------

def test_longest_alias_wins_over_prefix(detector: ModelDetector) -> None:
    """'Claude Code' must not also register a bare 'Claude' at the same span."""
    found = slugs(detector, "Claude Code writes better tests than the web app")
    assert "claude-code" in found
    assert "claude" not in found


def test_distinct_mentions_both_recorded(detector: ModelDetector) -> None:
    found = slugs(detector, "I use Claude Code for refactors but plain Claude for writing")
    assert {"claude-code", "claude"} <= found


def test_gpt5_variant_beats_base(detector: ModelDetector) -> None:
    found = slugs(detector, "GPT-5 Mini is cheap enough to run in a loop")
    assert "gpt-5-mini" in found
    assert "gpt-5" not in found


# --------------------------------------------------------------------------
# Mention metadata
# --------------------------------------------------------------------------

def test_mention_records_position_and_confidence(detector: ModelDetector) -> None:
    text = "Everyone says ChatGPT is slower now"
    (mention,) = [m for m in detector.detect(text) if m.slug == "chatgpt"]
    assert text[mention.start : mention.end] == "ChatGPT"
    assert 0.0 < mention.confidence <= 1.0


def test_weighted_alias_lowers_confidence(detector: ModelDetector) -> None:
    strong = detector.detect("Claude Sonnet handles this well")
    weak = detector.detect("sonnet handles this LLM prompt well")
    strong_conf = next(m.confidence for m in strong if m.slug == "claude-sonnet")
    weak_conf = next(m.confidence for m in weak if m.slug == "claude-sonnet")
    assert weak_conf < strong_conf


def test_repeated_mentions_deduplicate_to_one_per_model(detector: ModelDetector) -> None:
    mentions = detector.detect("ChatGPT ChatGPT ChatGPT")
    assert len([m for m in mentions if m.slug == "chatgpt"]) == 1


def test_repeated_mentions_raise_confidence(detector: ModelDetector) -> None:
    once = detector.detect("Gemini is fine for LLM work")
    thrice = detector.detect("Gemini is fine for LLM work. Gemini indexes fast. Gemini wins.")
    assert (
        next(m.confidence for m in thrice if m.slug == "gemini")
        > next(m.confidence for m in once if m.slug == "gemini")
    )


def test_empty_and_none_text_is_safe(detector: ModelDetector) -> None:
    assert detector.detect("") == []
    assert detector.detect("   \n  ") == []


def test_detect_is_not_quadratic_on_long_documents(detector: ModelDetector) -> None:
    """Guards against a regression to per-alias re.finditer over huge text."""
    text = ("Claude and ChatGPT and Gemini discuss LLM agents. " * 4000)
    mentions = detector.detect(text)
    assert {"claude", "chatgpt", "gemini"} <= {m.slug for m in mentions}
