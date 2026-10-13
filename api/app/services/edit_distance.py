"""Word-level edit distance calculator for cover letter drift tracking.

Uses Wagner-Fischer (Levenshtein) at the word token level.
Returns a float in [0.0, 1.0] where:
  0.0 = identical
  1.0 = completely different

This is used to track how much a user edits the AI draft before sending.
A lower edit distance over time = user trusts the agent more = higher autonomy.
"""
import re
from typing import List

# Cost cap: Levenshtein runs on at most MAX_TOKENS words per side (≤ ~1M cell updates).
# Words past the cap count as edits (an upper bound), so long inputs never go O(n*m).
MAX_TOKENS = 1000


def _tokenize(text: str) -> List[str]:
    """Split text into lowercase word tokens, stripping punctuation."""
    return re.findall(r"[a-zA-Z0-9']+", text.lower())


def word_edit_distance_pct(original: str, edited: str) -> float:
    """Return the fraction of word-level edits between original and edited.

    Levenshtein distance at word granularity, normalized by max(len(a), len(b)).
    Returns 0.0 if both strings are empty or identical.
    """
    a = _tokenize(original)
    b = _tokenize(edited)

    if not a and not b:
        return 0.0
    if not a:
        return 1.0
    if not b:
        return 1.0

    la, lb = len(a), len(b)
    tail = max(la - MAX_TOKENS, lb - MAX_TOKENS, 0)
    a, b = a[:MAX_TOKENS], b[:MAX_TOKENS]

    # Wagner-Fischer DP
    prev = list(range(len(b) + 1))
    for i, wa in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, wb in enumerate(b, 1):
            if wa == wb:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j - 1], prev[j], curr[j - 1])
        prev = curr

    dist = prev[len(b)] + tail
    return round(min(dist / max(la, lb), 1.0), 4)
