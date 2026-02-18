"""Tests for cover letter service clean_cover_letter function."""
from app.services.cover_letter import clean_cover_letter


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
