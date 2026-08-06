"""Text normalisation shared by the collectors."""

from __future__ import annotations

import html
import re

_BR = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_P = re.compile(r"<\s*/?\s*p\s*>", re.IGNORECASE)
_SCRIPT = re.compile(r"<(script|style).*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Reduce stored markup to readable prose.

    Runs twice on purpose. Hacker News stores comments with *escaped* markup
    (`&lt;b&gt;Claude&lt;/b&gt;`), so a single strip-then-unescape pass leaves
    literal `<b>` in the output and feeds it to the analyzer as if it were
    prose. Stripping again after unescaping catches what the entities were
    hiding.
    """
    for _ in range(2):
        before = text
        text = _SCRIPT.sub(" ", text)
        text = _BR.sub("\n", text)
        text = _P.sub("\n\n", text)
        text = _TAG.sub("", text)
        text = html.unescape(text)
        if text == before:
            break
    return text.strip()
