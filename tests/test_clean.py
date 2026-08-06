"""Boilerplate removal.

Cases are taken verbatim from the first live GitHub corpus, where 18.6% of
mentions turned out to be machine attribution rather than human opinion.
"""

from __future__ import annotations

import pytest

from pulseai.pipeline.clean import clean, is_bot
from pulseai.pipeline.detect import ModelDetector
from pulseai.registry import MODELS


@pytest.fixture(scope="module")
def detector() -> ModelDetector:
    return ModelDetector.from_specs(MODELS)


def test_strips_co_authored_trailer() -> None:
    text = (
        "Fix the cache invalidation bug.\n\n"
        "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
    )
    result = clean(text)
    assert "Co-Authored-By" not in result.text
    assert "Opus" not in result.text
    assert "Fix the cache invalidation bug." in result.text


def test_strips_assisted_by_trailer() -> None:
    result = clean("Refactor.\nAssisted-by: Claude Code:claude-opus-5 [Claude Code]")
    assert "claude-opus-5" not in result.text
    assert "Refactor." in result.text


def test_strips_generated_with_footer() -> None:
    result = clean("Real content here.\n\n🤖 Generated with [Claude Code](https://claude.com)")
    assert "Claude Code" not in result.text
    assert "Real content here." in result.text


def test_strips_ai_model_trailer() -> None:
    result = clean("Le correctif.\n--- AI-model: Claude Opus 5 (GitHub Copilot CLI)")
    assert "Opus" not in result.text
    assert "Le correctif." in result.text


def test_strips_html_comment_templates() -> None:
    """Template placeholders are the template author's words, not the reporter's."""
    text = (
        "### Usage\n"
        "<!-- What model did you use the tool with? Example: GPT5.5 high, "
        "Claude Opus 4.8 xhigh... -->\n"
        "Fully automated."
    )
    result = clean(text)
    assert "Opus" not in result.text
    assert "GPT5.5" not in result.text
    assert "Fully automated." in result.text


def test_preserves_human_text_above_the_trailer() -> None:
    """The whole point: a real opinion with a robot signature is still real."""
    text = (
        "Honestly Claude has been excellent for this refactor, way better than before.\n\n"
        "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
    )
    result = clean(text)
    assert "excellent for this refactor" in result.text
    assert "Co-Authored-By" not in result.text


def test_prose_mentioning_generation_survives() -> None:
    """Anchoring to line starts keeps ordinary sentences intact."""
    text = "The docs were generated with a script, and Claude helped me review them."
    result = clean(text)
    assert "Claude helped me review them" in result.text


def test_reports_how_much_was_removed() -> None:
    result = clean("Body.\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>")
    assert result.removed_chars > 0


def test_empty_and_none_are_safe() -> None:
    assert clean(None).text == ""
    assert clean("").is_empty
    assert clean("   ").is_empty


def test_document_of_pure_boilerplate_becomes_empty() -> None:
    result = clean("Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>")
    assert result.is_empty


@pytest.mark.parametrize(
    "author",
    ["dependabot[bot]", "renovate[bot]", "github-actions[bot]", "Dependabot", "some-tool[bot]"],
)
def test_bot_authors_recognised(author: str) -> None:
    assert is_bot(author)


@pytest.mark.parametrize("author", ["ajaiupadhyaya", "torvalds", None, "", "robotics-fan"])
def test_humans_not_flagged_as_bots(author: str | None) -> None:
    assert not is_bot(author)


# ---------------------------------------------------------------------------
# The behaviour that actually matters: cleaning changes what gets detected
# ---------------------------------------------------------------------------


def test_attribution_only_document_yields_no_mentions(detector: ModelDetector) -> None:
    text = (
        "Enable eslint max-depth rule and fix infringements\n\n"
        "Bumps the rule and fixes 12 call sites.\n\n"
        "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
    )
    assert "claude-opus" in {m.slug for m in detector.detect(text)}
    assert detector.detect(clean(text).text) == []


def test_genuine_discussion_still_detected_after_cleaning(detector: ModelDetector) -> None:
    text = (
        "Switched the extraction prompts to use the Sonnet/Opus escalation logic "
        "and it cut our LLM costs in half.\n\n"
        "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
    )
    assert "claude-opus" in {m.slug for m in detector.detect(clean(text).text)}
