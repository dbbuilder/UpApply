"""Tests for cover letter service functions."""
import pytest
from unittest.mock import MagicMock
from app.services.cover_letter import (
    append_closing,
    append_prototype_url,
    build_system_prompt,
    clean_cover_letter,
)


def test_clean_removes_subject_line():
    text = "Subject: Application for Developer\n\nI am writing to apply."
    result = clean_cover_letter(text)
    assert "Subject:" not in result
    assert "I am writing to apply." in result


def test_clean_removes_dear_salutation():
    text = "Dear Hiring Manager,\n\nI would be a great fit."
    result = clean_cover_letter(text)
    assert "Dear" not in result
    assert "I would be a great fit." in result


def test_clean_removes_signature_block():
    text = "I can start immediately.\n\nSincerely,\nJohn Doe"
    result = clean_cover_letter(text)
    assert "Sincerely" not in result
    assert "I can start immediately." in result


def test_clean_removes_best_regards():
    text = "Looking forward to working together.\n\nBest regards,\nJane"
    result = clean_cover_letter(text)
    assert "Best regards" not in result


def test_clean_removes_bracketed_placeholders():
    text = "I am [Your Name] and I work at [Company]."
    result = clean_cover_letter(text)
    assert "[Your Name]" not in result
    assert "[Company]" not in result


def test_clean_collapses_extra_newlines():
    text = "First paragraph.\n\n\n\n\nSecond paragraph."
    result = clean_cover_letter(text)
    assert "\n\n\n" not in result


def test_clean_preserves_normal_content():
    text = "I have 5 years of Python experience. My recent project involved building a REST API with FastAPI and PostgreSQL."
    result = clean_cover_letter(text)
    assert result == text


def test_clean_handles_empty_string():
    assert clean_cover_letter("") == ""


def test_clean_handles_whitespace_only():
    assert clean_cover_letter("   \n\n  ") == ""


def test_clean_combined_unwanted_elements():
    text = """Subject: Application

Dear Hiring Manager,

I have built several web applications using React and Python.

My experience includes a successful e-commerce platform.

Best regards,
John Smith"""
    result = clean_cover_letter(text)
    assert "Subject:" not in result
    assert "Dear" not in result
    assert "Best regards" not in result
    assert "e-commerce platform" in result


# ── append_closing ────────────────────────────────────────────────────────────

def test_append_closing_adds_warm_regards():
    text = "Here is my proposal."
    result = append_closing(text, "Warm regards,")
    assert result == "Here is my proposal.\n\nWarm regards,"


def test_append_closing_none_returns_unchanged():
    text = "Here is my proposal."
    assert append_closing(text, None) == text


def test_append_closing_empty_string_returns_unchanged():
    text = "Here is my proposal."
    assert append_closing(text, "") == text


def test_append_closing_custom_closing():
    text = "Thanks for your time."
    result = append_closing(text, "Best,\nChris")
    assert result.endswith("Best,\nChris")


# ── append_prototype_url ──────────────────────────────────────────────────────

def test_append_prototype_url_adds_sentence():
    text = "My cover letter body."
    result = append_prototype_url(text, "https://demo.example.com")
    assert "https://demo.example.com" in result
    assert result.startswith("My cover letter body.")


def test_append_prototype_url_none_returns_unchanged():
    text = "My cover letter body."
    assert append_prototype_url(text, None) == text


def test_append_prototype_url_empty_string_returns_unchanged():
    text = "My cover letter body."
    assert append_prototype_url(text, "") == text


def test_append_prototype_url_strips_whitespace():
    text = "Body."
    result = append_prototype_url(text, "  https://demo.example.com  ")
    assert "https://demo.example.com" in result
    assert "  https://" not in result


# ── Banned phrases ────────────────────────────────────────────────────────────

BANNED_PHRASES = [
    "I am well-equipped",
    "unique blend of skills",
    "align perfectly with your needs",
    "I am excited to apply",
    "I look forward to hearing from you",
    "my skills directly translate",
    "I am passionate about",
    "leverage my expertise",
    "I believe I would be a great fit",
    "I am confident that",
    "I would love the opportunity",
    "I am a perfect fit",
    "I am writing to",
    "I am reaching out",
]


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_clean_preserves_banned_phrases_in_body(phrase):
    """clean_cover_letter doesn't strip banned phrases — they are a prompt concern.
    This test documents that the function does NOT remove them (that's the AI's job).
    The phrases should pass through so the cover letter reviewer can catch regressions
    if the prompt is inadvertently changed to allow them."""
    text = f"My background includes {phrase} the specific domain knowledge you need."
    result = clean_cover_letter(text)
    # clean_cover_letter does NOT strip banned phrases — they are caught at generation time
    assert phrase in result, (
        f"clean_cover_letter should not strip banned phrase '{phrase}'; "
        "removing it here would hide generation regressions"
    )


def test_clean_preserves_warm_regards():
    """'Warm regards,' must survive clean_cover_letter — it is the required sign-off."""
    text = "Thank you for reading.\n\nWarm regards,"
    result = clean_cover_letter(text)
    assert "Warm regards," in result


def test_clean_removes_best_regards_but_not_warm_regards():
    """Only generic sign-offs are stripped; 'Warm regards,' is preserved."""
    text = "Body text.\n\nBest regards,\nAlice"
    result = clean_cover_letter(text)
    assert "Best regards" not in result
    assert "Warm regards" not in result  # not present, so nothing to preserve here


def test_warm_regards_preserved_when_present_with_other_signoffs():
    """If both appear, 'Warm regards,' survives and 'Sincerely,' is stripped."""
    text = "Body.\n\nSincerely,\nSomeone\n\nWarm regards,"
    result = clean_cover_letter(text)
    assert "Warm regards," in result


# ── build_system_prompt — banned phrases documented in prompt ─────────────────

def _mock_profile(**kwargs):
    p = MagicMock()
    p.full_name = kwargs.get("full_name", "Chris Therriault")
    p.professional_title = kwargs.get("professional_title", "Senior Developer")
    p.bio = kwargs.get("bio", "20 years building SaaS products.")
    p.career_goals = kwargs.get("career_goals", None)
    p.communication_style = kwargs.get("communication_style", None)
    p.unique_strengths = kwargs.get("unique_strengths", [])
    p.proposal_anchors = kwargs.get("proposal_anchors", {})
    return p


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_system_prompt_documents_each_banned_phrase(phrase):
    """Every banned phrase must appear in the system prompt so the model sees it."""
    prompt = build_system_prompt(_mock_profile())
    assert phrase in prompt, f"Banned phrase missing from system prompt: {phrase!r}"


def test_system_prompt_requires_warm_regards_close():
    prompt = build_system_prompt(_mock_profile())
    assert "Warm regards," in prompt


def test_system_prompt_forbids_opening_with_i():
    prompt = build_system_prompt(_mock_profile())
    assert "NEVER" in prompt and '"I"' in prompt


def test_system_prompt_includes_call_offer_by_default():
    prompt = build_system_prompt(_mock_profile())
    assert "no-cost call" in prompt.lower() or "no cost" in prompt.lower()


def test_system_prompt_omits_call_offer_when_disabled():
    prompt = build_system_prompt(_mock_profile(), include_call_offer=False)
    assert "Skip the call offer" in prompt


def test_system_prompt_includes_always_include_items():
    profile = _mock_profile(
        proposal_anchors={"always_include": ["SchoolVision 20yr SaaS", "MBA"]}
    )
    prompt = build_system_prompt(profile)
    assert "SchoolVision 20yr SaaS" in prompt
    assert "MBA" in prompt
