"""Unit tests for the word-level edit distance (bounded cost on long inputs)."""
import time

from app.services.edit_distance import MAX_TOKENS, word_edit_distance_pct


def test_identical_and_empty():
    assert word_edit_distance_pct("a b c", "a b c") == 0.0
    assert word_edit_distance_pct("", "") == 0.0
    assert word_edit_distance_pct("", "a") == 1.0


def test_small_edit_is_exact():
    assert word_edit_distance_pct("one two three four", "one two 3 four") == 0.25


def test_long_inputs_are_bounded_cost():
    a = " ".join(f"w{i}" for i in range(5000))
    b = " ".join(f"v{i}" for i in range(5000))
    start = time.monotonic()
    pct = word_edit_distance_pct(a, b)
    assert time.monotonic() - start < 2.0
    assert pct == 1.0


def test_tail_beyond_cap_counts_as_edits():
    base = " ".join(f"w{i}" for i in range(MAX_TOKENS))
    extra = " ".join(f"x{i}" for i in range(MAX_TOKENS))
    # identical first MAX_TOKENS words, then MAX_TOKENS added words -> half changed
    assert word_edit_distance_pct(base, base + " " + extra) == 0.5
