"""Sentiment analysis, per model, per document.

Two implementations behind one protocol:

* `HeuristicAnalyzer` — a lexicon tuned for developer vocabulary. No downloads,
  no GPU, runs in tests. General-purpose lexicons like VADER misread this
  domain badly ("this model is insane at refactoring" is praise), so the word
  list is hand-weighted for how engineers actually talk about tooling.
* `LocalAnalyzer` — a RoBERTa sentiment model running on-device. Better, but
  needs `uv sync --extra ml` and a one-time model download.

An LLM-backed analyzer implements the same protocol without callers changing.

Scoring is *aspect-aware*: a document comparing two models is positive about one
and negative about the other, so each model is scored over a window around its
own mentions rather than over the whole document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

import structlog

from pulseai.config import Settings, get_settings

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SentimentScore:
    positive: float
    negative: float
    neutral: float
    confidence: float
    analyzer: str

    @property
    def compound(self) -> float:
        """Single signed number in [-1, 1] for timeseries and averages."""
        return round(self.positive - self.negative, 4)

    @classmethod
    def neutral_result(cls, analyzer: str) -> SentimentScore:
        return cls(positive=0.0, negative=0.0, neutral=1.0, confidence=0.0, analyzer=analyzer)


class Analyzer(Protocol):
    name: str

    def score(self, text: str) -> SentimentScore: ...


# ---------------------------------------------------------------------------
# Heuristic
# ---------------------------------------------------------------------------

#: Weights are deliberately asymmetric. Complaints in developer forums are
#: stated plainly ("it's broken"); praise is hedged ("pretty good actually").
#: Equal weighting would make every source look mildly negative.
_POSITIVE: dict[str, float] = {
    "amazing": 1.0, "excellent": 1.0, "fantastic": 1.0, "brilliant": 0.9, "superb": 1.0,
    "love": 0.9, "loves": 0.9, "loved": 0.9, "awesome": 0.9, "great": 0.7, "good": 0.5,
    "better": 0.6, "best": 0.9, "impressive": 0.8, "impressed": 0.8, "solid": 0.6,
    "reliable": 0.7, "fast": 0.6, "faster": 0.6, "cheap": 0.5, "cheaper": 0.5,
    "accurate": 0.8, "helpful": 0.7, "useful": 0.6, "intuitive": 0.7, "smooth": 0.6,
    "powerful": 0.7, "capable": 0.6, "recommend": 0.8, "recommended": 0.8,
    "works": 0.4, "worked": 0.4, "nails": 0.8, "nailed": 0.8, "crushed": 0.7,
    "seamless": 0.8, "elegant": 0.7, "clean": 0.5, "wins": 0.6, "winner": 0.7,
    "underrated": 0.6, "gamechanger": 1.0, "godsend": 1.0, "worth": 0.5,
    "delightful": 0.9, "polished": 0.7, "stable": 0.6, "consistent": 0.6,
    # Developer slang where the literal sense is negative.
    "insane": 0.7, "crazy": 0.5, "sick": 0.6, "nuts": 0.5, "ridiculous": 0.4,
    "stupid": 0.3,  # as in "stupid fast"; the bigram rule below handles it
    "beast": 0.8, "banger": 0.9, "goat": 0.9, "slaps": 0.8,
}

_NEGATIVE: dict[str, float] = {
    "terrible": 1.0, "awful": 1.0, "horrible": 1.0, "garbage": 1.0, "trash": 1.0,
    "useless": 1.0, "broken": 0.9, "buggy": 0.8, "bug": 0.4, "bugs": 0.5,
    "hate": 0.9, "hates": 0.9, "hated": 0.9, "worst": 1.0, "worse": 0.7, "bad": 0.7,
    "slow": 0.7, "slower": 0.7, "sluggish": 0.8, "laggy": 0.8, "expensive": 0.7,
    "overpriced": 0.9, "pricey": 0.6, "wrong": 0.6, "fails": 0.8, "failed": 0.8,
    "failing": 0.8, "fail": 0.7, "crash": 0.8, "crashes": 0.8, "crashed": 0.8,
    "error": 0.5, "errors": 0.5, "hallucinate": 0.8, "hallucinates": 0.8,
    "hallucinating": 0.8, "hallucination": 0.8, "hallucinations": 0.8,
    "lazy": 0.7, "dumb": 0.8, "disappointing": 0.9, "disappointed": 0.9,
    "regression": 0.8, "regressed": 0.8, "nerfed": 0.9, "downgrade": 0.8,
    "unusable": 1.0, "frustrating": 0.9, "frustrated": 0.9, "annoying": 0.7,
    "annoyed": 0.7, "confusing": 0.6, "limited": 0.5, "limits": 0.4,
    "ratelimit": 0.7, "throttled": 0.7, "censored": 0.6, "refuses": 0.7,
    "refusal": 0.7, "refusals": 0.7, "gaslighting": 0.8, "mediocre": 0.8,
    "meh": 0.6, "sucks": 1.0, "sucked": 1.0, "flaky": 0.8, "unreliable": 0.9,
    "clunky": 0.7, "bloated": 0.6, "misleading": 0.7, "cancelled": 0.5,
    "cancelling": 0.5, "canceled": 0.5, "downtime": 0.7, "outage": 0.8,
}

_NEGATORS = frozenset(
    {"not", "no", "never", "none", "cannot", "cant", "can't", "won't", "wont",
     "doesn't", "doesnt", "didn't", "didnt", "isn't", "isnt", "aren't", "arent",
     "wasn't", "wasnt", "nothing", "nor", "without", "hardly", "barely", "rarely"}
)

_INTENSIFIERS: dict[str, float] = {
    "very": 1.4, "really": 1.3, "extremely": 1.7, "incredibly": 1.6, "insanely": 1.6,
    "super": 1.4, "so": 1.2, "absolutely": 1.5, "completely": 1.4, "totally": 1.3,
    "utterly": 1.6, "way": 1.3, "far": 1.3, "much": 1.2, "stupid": 1.5,
    "slightly": 0.6, "somewhat": 0.7, "kinda": 0.7, "kind": 0.8, "a": 1.0,
    "bit": 0.6, "fairly": 0.8, "pretty": 0.9, "quite": 1.1, "mildly": 0.6,
}

#: Bigrams whose meaning inverts or intensifies the second word. Handled before
#: unigram scoring so "stupid fast" never contributes negative weight.
_BIGRAM_OVERRIDES: dict[tuple[str, str], float] = {
    ("stupid", "fast"): 0.9,
    ("stupid", "good"): 0.9,
    ("stupid", "cheap"): 0.8,
    ("insanely", "good"): 1.0,
    ("dirt", "cheap"): 0.8,
    ("blazing", "fast"): 0.9,
    ("rock", "solid"): 0.9,
    ("dead", "simple"): 0.8,
    ("game", "changer"): 1.0,
    ("no", "brainer"): 0.8,
    ("rate", "limits"): -0.7,
    ("rate", "limited"): -0.7,
    ("context", "rot"): -0.7,
    ("waste", "of"): -0.8,
    ("falls", "apart"): -0.9,
    ("gave", "up"): -0.6,
    ("switched", "away"): -0.7,
    ("cancelled", "my"): -0.8,
    ("canceled", "my"): -0.8,
}

_TOKEN_RE = re.compile(r"[a-z0-9']+")

#: Controls how quickly accumulated sentiment weight approaches ±1. At 4.0 a
#: single strong word lands near 0.45 and a sustained rant near 0.95, which
#: leaves room for "emphatic" to outrank "mildly negative" instead of both
#: saturating.
_SQUASH_ALPHA = 4.0


def _squash(value: float) -> float:
    """Map an unbounded weight sum into (-1, 1), preserving order and sign."""
    return value / ((value * value + _SQUASH_ALPHA) ** 0.5)


class HeuristicAnalyzer:
    """Lexicon scorer with negation, intensifiers, and bigram overrides."""

    name = "heuristic"

    #: Beyond this many signal words, more evidence should not keep raising
    #: confidence — a rant repeating "broken" six times is not six times surer.
    _CONFIDENCE_SATURATION = 6

    def score(self, text: str) -> SentimentScore:
        if not text or not text.strip():
            return SentimentScore.neutral_result(self.name)

        tokens = _TOKEN_RE.findall(text.lower())
        if not tokens:
            return SentimentScore.neutral_result(self.name)

        positive_sum = 0.0
        negative_sum = 0.0
        hits = 0
        index = 0

        while index < len(tokens):
            token = tokens[index]

            if index + 1 < len(tokens):
                override = _BIGRAM_OVERRIDES.get((token, tokens[index + 1]))
                if override is not None:
                    if override > 0:
                        positive_sum += override
                    else:
                        negative_sum += -override
                    hits += 1
                    index += 2
                    continue

            weight = _POSITIVE.get(token)
            polarity = 1
            if weight is None:
                weight = _NEGATIVE.get(token)
                polarity = -1
            if weight is None:
                index += 1
                continue

            multiplier = 1.0
            negated = False
            for back in range(1, 4):
                if index - back < 0:
                    break
                previous = tokens[index - back]
                if previous in _NEGATORS:
                    negated = True
                    break
                if back == 1 and previous in _INTENSIFIERS:
                    multiplier = _INTENSIFIERS[previous]

            value = weight * multiplier
            if negated:
                # Negation weakens rather than mirrors: "not great" is lukewarm,
                # not the equal-and-opposite of "great".
                polarity *= -1
                value *= 0.6

            if polarity > 0:
                positive_sum += value
            else:
                negative_sum += value
            hits += 1
            index += 1

        if hits == 0:
            return SentimentScore.neutral_result(self.name)

        if text.count("!") >= 1:
            boost = 1.0 + min(text.count("!"), 3) * 0.05
            positive_sum *= boost
            negative_sum *= boost

        # Normalising positive/negative to sum to 1 would throw away magnitude:
        # "good" and "absolutely fantastic" both become 1.0 positive, and no
        # intensifier or negation could ever move the number. Squashing the raw
        # sums instead keeps intensity, and keeps the result bounded.
        net = positive_sum - negative_sum
        total = positive_sum + negative_sum
        compound = _squash(net)
        magnitude = _squash(total)

        # magnitude >= |compound| because squash is monotonic and total >= |net|,
        # so neither component can come out negative.
        positive = (magnitude + compound) / 2
        negative = (magnitude - compound) / 2

        # Sparse signal in a long document should not read as a confident call.
        density = min(hits / self._CONFIDENCE_SATURATION, 1.0)
        confidence = round(density * (0.4 + 0.6 * abs(compound)), 4)

        return SentimentScore(
            positive=round(positive, 4),
            negative=round(negative, 4),
            neutral=round(1.0 - magnitude, 4),
            confidence=confidence,
            analyzer=self.name,
        )


# ---------------------------------------------------------------------------
# Local transformer
# ---------------------------------------------------------------------------


class LocalAnalyzer:
    """RoBERTa sentiment running on-device via HuggingFace transformers.

    Loaded lazily so importing this module never triggers a model download, and
    so a machine without the `ml` extra can still import the package.
    """

    name = "local"
    MODEL_ID = "cardiffnlp/twitter-roberta-base-sentiment-latest"
    #: The model's positional limit. Longer text is truncated by the tokenizer.
    MAX_TOKENS = 512

    def __init__(self) -> None:
        self._pipeline = None

    @staticmethod
    def is_available() -> bool:
        import importlib.util

        return all(
            importlib.util.find_spec(module) is not None
            for module in ("torch", "transformers")
        )

    def _ensure_loaded(self):
        if self._pipeline is not None:
            return self._pipeline

        import torch
        from transformers import pipeline

        device = -1
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = 0

        log.info("analyzer.loading", model=self.MODEL_ID, device=str(device))
        self._pipeline = pipeline(
            "sentiment-analysis",
            model=self.MODEL_ID,
            device=device,
            truncation=True,
            max_length=self.MAX_TOKENS,
            top_k=None,
        )
        return self._pipeline

    def score(self, text: str) -> SentimentScore:
        if not text or not text.strip():
            return SentimentScore.neutral_result(self.name)

        classifier = self._ensure_loaded()
        results = classifier(text)[0]
        scores = {entry["label"].lower(): float(entry["score"]) for entry in results}

        positive = scores.get("positive", 0.0)
        negative = scores.get("negative", 0.0)
        neutral = scores.get("neutral", 0.0)

        return SentimentScore(
            positive=round(positive, 4),
            negative=round(negative, 4),
            neutral=round(neutral, 4),
            confidence=round(max(positive, negative, neutral), 4),
            analyzer=self.name,
        )


# ---------------------------------------------------------------------------
# Aspect windowing
# ---------------------------------------------------------------------------

#: Characters either side of a mention that count as "about" that model. Roughly
#: two sentences, which is where a comparison post switches subject.
ASPECT_WINDOW = 320


def aspect_text(text: str, positions: list[tuple[int, int]], window: int = ASPECT_WINDOW) -> str:
    """Extract the parts of `text` that discuss a model at the given spans.

    Overlapping windows are merged so a model mentioned three times in one
    paragraph contributes that paragraph once, not three times.
    """
    if not positions:
        return text

    spans = sorted((max(0, s - window), min(len(text), e + window)) for s, e in positions)
    merged: list[list[int]] = [list(spans[0])]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    return " ".join(text[start:end] for start, end in merged)


def get_analyzer(settings: Settings | None = None) -> Analyzer:
    """Resolve the configured analyzer, degrading rather than failing.

    `auto` prefers the local model and silently falls back to the heuristic when
    the ml extra is not installed — the pipeline must never be blocked on an
    optional dependency.
    """
    settings = settings or get_settings()

    if settings.analyzer == "heuristic":
        return HeuristicAnalyzer()

    if settings.analyzer == "local":
        if not LocalAnalyzer.is_available():
            raise RuntimeError(
                "PULSEAI_ANALYZER=local but transformers/torch are missing. "
                "Run: uv sync --extra ml"
            )
        return LocalAnalyzer()

    if LocalAnalyzer.is_available():
        return LocalAnalyzer()
    log.info("analyzer.fallback", reason="ml extra not installed", using="heuristic")
    return HeuristicAnalyzer()
