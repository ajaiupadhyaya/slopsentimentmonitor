"""Strip machine-generated text before analysis.

Measured on the first live corpus: **18.6% of all model mentions came from
boilerplate**, not from anyone's opinion. Three kinds dominate:

* Git attribution trailers — `Co-Authored-By: Claude Opus 5 <...>`,
  `Assisted-by: Claude Code:claude-opus-5`, `🤖 Generated with [Claude Code]`.
  A robot signature on a PR that renames a variable.
* HTML comments in GitHub issue templates — `<!-- Example: GPT5.5 high,
  Claude Opus 4.8 xhigh -->`. That is the *template author's* placeholder,
  present whether or not the reporter uses those models.
* Bot-authored bodies — dependabot, release-please and friends.

Counting these inflates mindshare for whichever assistant wrote the commit, and
worse, attaches the sentiment of an unrelated eslint fix to that model. Both
failures are invisible in aggregate: the numbers look plausible and are wrong.

The cleaner removes the boilerplate and keeps the rest, because a human comment
sitting above a `Co-Authored-By` trailer is still a real opinion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Trailers are commonly preceded by a separator, a markdown bullet, or quote
#: markers — "--- AI-model: Claude Opus 5" is the real-world form, not a bare
#: line start.
_LEAD = r"^[\s>*+\-–—_=]*"

#: Git/AI trailers. Anchored to line starts so prose that happens to contain
#: "generated with" survives.
_TRAILER_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(_LEAD + body + r".*$", re.IGNORECASE | re.MULTILINE)
    for body in (
        r"co-authored-by:",
        r"assisted-by:",
        r"signed-off-by:",
        r"ai-(?:model|session|agent|tool):",
        r"(?:generated|created)\s+(?:with|by)\s+\[",
        r"🤖\s*generated with",
        r"tools?/models?\s+used:",
    )
)

#: Issue/PR template scaffolding.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

#: Usernames whose output is never human opinion.
_BOT_AUTHORS: frozenset[str] = frozenset(
    {
        "dependabot", "dependabot[bot]", "renovate", "renovate[bot]",
        "github-actions", "github-actions[bot]", "release-please[bot]",
        "codecov[bot]", "sonarcloud[bot]", "greenkeeper[bot]", "snyk-bot",
        "allcontributors[bot]", "imgbot[bot]", "pre-commit-ci[bot]",
        "semantic-release-bot", "netlify[bot]", "vercel[bot]", "changeset-bot",
    }
)


@dataclass(frozen=True)
class CleanResult:
    text: str
    #: Characters removed as boilerplate. Kept for observability — a sudden jump
    #: means an upstream template changed.
    removed_chars: int
    is_bot_authored: bool

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


def is_bot(author: str | None) -> bool:
    if not author:
        return False
    normalised = author.strip().lower()
    return normalised in _BOT_AUTHORS or normalised.endswith("[bot]")


def clean(text: str | None, author: str | None = None) -> CleanResult:
    """Remove machine-generated regions, preserving whatever a human wrote."""
    if not text:
        return CleanResult(text="", removed_chars=0, is_bot_authored=is_bot(author))

    original_length = len(text)
    cleaned = _HTML_COMMENT.sub(" ", text)
    for pattern in _TRAILER_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # Collapse the blank lines the removals leave behind so aspect windows do
    # not spend their budget on whitespace.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    return CleanResult(
        text=cleaned,
        removed_chars=original_length - len(cleaned),
        is_bot_authored=is_bot(author),
    )
