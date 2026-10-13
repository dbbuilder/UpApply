"""Neutralise untrusted text (job posts, scraped pages, voice samples, memories) before it is
placed inside a delimited prompt block, so it can never form a tag and break out of the block."""
import html
import re
import unicodedata

# Untrusted text can never form a tag: after NFKC (folds fullwidth/small-form brackets),
# entity decoding and zero-width stripping, every angle bracket (literal or URL-encoded) is
# replaced with a look-alike. Linear time; nothing to bypass with tag-name variants.
_ZERO_WIDTH = re.compile("[­​-‏⁠﻿]")
_URL_BRACKET = re.compile("%3([ce])", re.IGNORECASE)
_BRACKETS = str.maketrans({"<": "‹", ">": "›"})


def decode_entities(text: str) -> str:
    """Decode HTML entities until a fixed point (any nesting depth). Each round that changes
    the string makes it shorter, so this always terminates."""
    while True:
        decoded = html.unescape(text)
        if decoded == text:
            return text
        text = decoded


def neutralise(text: str) -> str:
    for _ in range(10):  # NFKC can surface new entities (fullwidth "&") and vice versa
        normalised = decode_entities(unicodedata.normalize("NFKC", text))
        if normalised == text:
            break
        text = normalised
    text = _ZERO_WIDTH.sub("", text)
    text = _URL_BRACKET.sub(lambda m: "<" if m.group(1).lower() == "c" else ">", text)
    return unicodedata.normalize("NFKC", text).translate(_BRACKETS)


def escape_brackets(text: str) -> str:
    """For trusted text that must reach the model verbatim (the user's own prototype URL and
    extra points): no entity decoding or normalisation, only brackets swapped so it cannot
    close its delimiting block."""
    return text.translate(_BRACKETS)
