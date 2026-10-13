"""Neutralise untrusted text (job posts, scraped pages, voice samples, memories) before it is
placed inside a delimited prompt block, so it can never form a tag and break out of the block."""
import html
import re
import unicodedata

# Untrusted text can never form a tag or an entity: NFKC (folds fullwidth/small-form
# brackets and ampersands), one round of entity decoding, zero-width stripping and URL
# decoding of "<", ">" and "&" all run inside one bounded fixed-point loop, so no step can
# re-expose what an earlier step already passed. Then every "<", ">" and "&" left is
# swapped for a look-alike. Whatever the loop did not finish decoding is inert.
_ZERO_WIDTH = re.compile("[\u00ad\u200b-\u200f\u2060\ufeff]")
_URL_ESCAPE = re.compile("%(3c|3e|26)", re.IGNORECASE)
_URL_CHARS = {"3c": "<", "3e": ">", "26": "&"}
_BRACKETS = str.maketrans({"<": "\u2039", ">": "\u203a"})
_UNTRUSTED = str.maketrans({"<": "\u2039", ">": "\u203a", "&": "\uff06"})
_MAX_ROUNDS = 16
DEFAULT_MAX_CHARS = 50_000


def decode_entities(text: str) -> str:
    """Decode HTML entities until a fixed point (any nesting depth). Each round that changes
    the string makes it shorter, so this always terminates."""
    while True:
        decoded = html.unescape(text)
        if decoded == text:
            return text
        text = decoded


def _decode_round(text: str) -> str:
    text = html.unescape(unicodedata.normalize("NFKC", text))
    text = _ZERO_WIDTH.sub("", text)
    return _URL_ESCAPE.sub(lambda m: _URL_CHARS[m.group(1).lower()], text)


def neutralise(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """`max_chars` caps the OUTPUT: NFKC can expand a code point up to 18 chars (U+FDFA).
    Each round is clipped too, so the work stays bounded; the final translate is 1:1."""
    for _ in range(_MAX_ROUNDS):
        decoded = _decode_round(text)[:max_chars]
        if decoded == text:
            break
        text = decoded
    return unicodedata.normalize("NFKC", text).translate(_UNTRUSTED)[:max_chars]


def escape_brackets(text: str) -> str:
    """For trusted text that must reach the model verbatim (the user's own prototype URL and
    extra points): no entity decoding or normalisation, only brackets swapped so it cannot
    close its delimiting block."""
    return text.translate(_BRACKETS)
