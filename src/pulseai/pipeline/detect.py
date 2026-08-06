"""Find which LLMs a document is talking about.

Every metric in this platform is ultimately a count of these matches, so the
design optimises precision over recall. A missed mention costs a little recall;
a phantom mention silently corrupts a sentiment average and nobody notices.

Three mechanisms carry that precision:

1. **Boundaries** — matches must not sit inside a longer word, so "Casanova"
   never yields Nova and "codexes" never yields Codex.
2. **Case sensitivity** — "grok" is a verb, "Grok" is a product.
3. **Context gating** — genuinely ambiguous aliases ("Gemini", "Nova",
   "sonnet") only count when the rest of the document is about AI. The check
   masks the model's own matches first, so a name can never vouch for itself.

Plus a small blocklist for names attached to famous humans, which no amount of
context gating catches: Claude Monet is not a language model.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from pulseai.registry import AI_CONTEXT_TERMS, Alias, ModelSpec

#: A match may not be flanked by characters that would make it part of a longer
#: token. Deliberately excludes "-" and "." so "gpt-5" can match inside
#: "gpt-5-mini" and lose to it on length rather than being invisible.
_LEFT = r"(?<![A-Za-z0-9_])"
_RIGHT = r"(?![A-Za-z0-9_])"

#: Whitespace in an alias matches any run of space, hyphen or underscore, so a
#: single "claude code" alias covers "Claude-Code" and "claude_code" too.
_GAP = r"[\s\-_]+"


@dataclass(frozen=True)
class Mention:
    """One model, detected in one document."""

    slug: str
    name: str
    company: str
    #: Character offsets of the first occurrence.
    start: int
    end: int
    matched_text: str
    #: Number of distinct occurrences in the document.
    count: int
    confidence: float


@dataclass(frozen=True)
class _Candidate:
    slug: str
    start: int
    end: int
    text: str
    alias: Alias

    @property
    def length(self) -> int:
        return self.end - self.start


def _alias_pattern(text: str) -> str:
    core = _GAP.join(re.escape(part) for part in text.split())
    return f"{_LEFT}{core}{_RIGHT}"


def _context_pattern(terms: Iterable[str]) -> re.Pattern[str]:
    # Longest first so "context window" wins over a bare "context" if both are
    # ever present in the term set.
    ordered = sorted(terms, key=len, reverse=True)
    body = "|".join(_GAP.join(re.escape(p) for p in t.split()) for t in ordered)
    return re.compile(rf"{_LEFT}(?:{body})s?{_RIGHT}", re.IGNORECASE)


class ModelDetector:
    """Compiled alias matcher over a fixed catalog of models.

    Construction is expensive and matching is not: build one and reuse it. All
    aliases compile into two master regexes (one per case-sensitivity class), so
    scanning a document is linear in its length regardless of catalog size.
    """

    def __init__(
        self,
        entries: list[tuple[str, str, str, Alias]],
        context_terms: Iterable[str] = AI_CONTEXT_TERMS,
    ) -> None:
        self._meta: dict[str, tuple[str, str]] = {
            slug: (name, company) for slug, name, company, _ in entries
        }
        self._aliases: list[tuple[str, Alias]] = [
            (slug, alias) for slug, _, _, alias in entries
        ]
        self._ci = self._compile(
            [(i, a) for i, (_, a) in enumerate(self._aliases) if not a.case_sensitive],
            re.IGNORECASE,
        )
        self._cs = self._compile(
            [(i, a) for i, (_, a) in enumerate(self._aliases) if a.case_sensitive],
            0,
        )
        self._context = _context_pattern(context_terms)

    @classmethod
    def from_specs(cls, specs: Iterable[ModelSpec]) -> ModelDetector:
        entries: list[tuple[str, str, str, Alias]] = [
            (spec.slug, spec.name, spec.company, alias)
            for spec in specs
            for alias in spec.all_aliases()
        ]
        return cls(entries)

    @staticmethod
    def _compile(
        items: list[tuple[int, Alias]], flags: int
    ) -> tuple[re.Pattern[str], dict[str, int]] | None:
        if not items:
            return None
        groups: dict[str, int] = {}
        parts: list[str] = []
        # Alternation in Python's `re` is first-match, not longest-match, and
        # finditer resumes past the end of whatever matched. Without this sort,
        # the "claude" branch consumes the word and "Claude Code" is never even
        # attempted. Longest alias first makes the specific name win.
        for idx, alias in sorted(items, key=lambda pair: -len(pair[1].text)):
            group = f"g{idx}"
            groups[group] = idx
            parts.append(f"(?P<{group}>{_alias_pattern(alias.text)})")
        return re.compile("|".join(parts), flags), groups

    # ------------------------------------------------------------------

    def detect(self, text: str | None) -> list[Mention]:
        if not text or not text.strip():
            return []

        candidates = self._scan(text)
        candidates = [c for c in candidates if not self._is_blocked(text, c)]
        accepted = self._resolve_overlaps(candidates)
        return self._aggregate(text, accepted)

    def _scan(self, text: str) -> list[_Candidate]:
        found: list[_Candidate] = []
        for compiled in (self._ci, self._cs):
            if compiled is None:
                continue
            pattern, groups = compiled
            for match in pattern.finditer(text):
                key = match.lastgroup
                if key is None:
                    continue
                slug, alias = self._aliases[groups[key]]
                found.append(
                    _Candidate(
                        slug=slug,
                        start=match.start(),
                        end=match.end(),
                        text=match.group(),
                        alias=alias,
                    )
                )
        return found

    def _is_blocked(self, text: str, candidate: _Candidate) -> bool:
        """Reject matches followed by a word that reveals a different referent."""
        if not candidate.alias.blocked_next:
            return False
        tail = text[candidate.end : candidate.end + 40]
        following = re.match(r"[\s\-]+([A-Za-zÀ-ÿ'’\-]+)", tail)
        if not following:
            return False
        return following.group(1).lower() in candidate.alias.blocked_next

    @staticmethod
    def _resolve_overlaps(candidates: list[_Candidate]) -> list[_Candidate]:
        """Longest match wins, so "Claude Code" suppresses the "Claude" inside it.

        Ties break on earlier position purely for determinism.
        """
        ordered = sorted(candidates, key=lambda c: (-c.length, c.start))
        accepted: list[_Candidate] = []
        taken: list[tuple[int, int]] = []
        for cand in ordered:
            if any(cand.start < end and start < cand.end for start, end in taken):
                continue
            accepted.append(cand)
            taken.append((cand.start, cand.end))
        return accepted

    def _aggregate(self, text: str, accepted: list[_Candidate]) -> list[Mention]:
        by_slug: dict[str, list[_Candidate]] = {}
        for cand in accepted:
            by_slug.setdefault(cand.slug, []).append(cand)

        mentions: list[Mention] = []
        for slug, cands in by_slug.items():
            if not self._context_satisfied(text, cands):
                continue
            cands.sort(key=lambda c: c.start)
            first = cands[0]
            name, company = self._meta[slug]
            mentions.append(
                Mention(
                    slug=slug,
                    name=name,
                    company=company,
                    start=first.start,
                    end=first.end,
                    matched_text=first.text,
                    count=len(cands),
                    confidence=self._confidence(cands),
                )
            )
        mentions.sort(key=lambda m: (-m.confidence, m.start))
        return mentions

    def _context_satisfied(self, text: str, cands: list[_Candidate]) -> bool:
        """Ambiguous aliases need AI context from somewhere other than themselves.

        If any matched alias for this model is unambiguous, the model is
        confirmed outright — "Claude Sonnet" needs no help even though a bare
        "sonnet" would.
        """
        if any(not c.alias.requires_context for c in cands):
            return True
        masked = list(text)
        for cand in cands:
            masked[cand.start : cand.end] = " " * cand.length
        return self._context.search("".join(masked)) is not None

    @staticmethod
    def _confidence(cands: list[_Candidate]) -> float:
        """Best alias weight, nudged upward by repetition.

        Repetition is weak evidence, so it moves confidence asymptotically
        toward the alias weight rather than to certainty: one mention scores
        0.70x, two 0.85x, and it never quite reaches 1.0x.
        """
        weight = max(c.alias.weight for c in cands)
        occurrences = len(cands)
        factor = 0.70 + 0.30 * (1 - 1 / occurrences)
        return round(min(1.0, weight * factor), 4)
