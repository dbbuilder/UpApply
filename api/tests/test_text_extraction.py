"""Unit tests for app.services.text_extraction (no DB, no real OpenAI)."""
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# extract_text_from_pdf
# ---------------------------------------------------------------------------

def _mock_pdfplumber(pages_text: list):
    """Return a mock pdfplumber module whose open() yields given page texts."""
    mock_module = MagicMock()
    mock_pages = []
    for text in pages_text:
        p = MagicMock()
        p.extract_text.return_value = text
        mock_pages.append(p)
    mock_pdf_ctx = MagicMock()
    mock_pdf_ctx.__enter__ = MagicMock(return_value=mock_pdf_ctx)
    mock_pdf_ctx.__exit__ = MagicMock(return_value=False)
    mock_pdf_ctx.pages = mock_pages
    mock_module.open.return_value = mock_pdf_ctx
    return mock_module


@pytest.mark.asyncio
async def test_extract_pdf_returns_page_text():
    import sys
    mock_pp = _mock_pdfplumber(["Page one content"])
    with patch.dict(sys.modules, {"pdfplumber": mock_pp}):
        import importlib
        import app.services.text_extraction as mod
        importlib.reload(mod)
        result = await mod.extract_text_from_pdf(b"%PDF fake bytes")
        importlib.reload(mod)

    assert result == "Page one content"


@pytest.mark.asyncio
async def test_extract_pdf_skips_empty_pages():
    import sys
    mock_pp = _mock_pdfplumber(["Real text", None])
    with patch.dict(sys.modules, {"pdfplumber": mock_pp}):
        import importlib
        import app.services.text_extraction as mod
        importlib.reload(mod)
        result = await mod.extract_text_from_pdf(b"%PDF")
        importlib.reload(mod)

    assert result == "Real text"


@pytest.mark.asyncio
async def test_extract_pdf_raises_when_pdfplumber_missing():
    import sys
    with patch.dict(sys.modules, {"pdfplumber": None}):
        import importlib
        import app.services.text_extraction as mod
        importlib.reload(mod)
        with pytest.raises(ImportError, match="pdfplumber"):
            await mod.extract_text_from_pdf(b"bytes")
        importlib.reload(mod)


# ---------------------------------------------------------------------------
# extract_text_from_image (OCR via OpenAI)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_image_calls_openai_and_returns_text():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "  Extracted OCR text  "

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.text_extraction.get_openai_client", return_value=mock_client):
        from app.services.text_extraction import extract_text_from_image
        result = await extract_text_from_image(b"\x89PNG", "image/png")

    assert result == "Extracted OCR text"
    mock_client.chat.completions.create.assert_awaited_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["max_tokens"] == 4000


@pytest.mark.asyncio
async def test_extract_image_uses_settings_default_model():
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "text"
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.text_extraction.get_openai_client", return_value=mock_client), \
         patch("app.services.text_extraction.settings") as mock_settings:
        mock_settings.default_model = "gpt-4o-mini"
        from app.services.text_extraction import extract_text_from_image
        await extract_text_from_image(b"bytes", "image/jpeg")

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_extract_image_propagates_openai_error():
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("API down"))

    with patch("app.services.text_extraction.get_openai_client", return_value=mock_client):
        from app.services.text_extraction import extract_text_from_image
        with pytest.raises(RuntimeError, match="API down"):
            await extract_text_from_image(b"bytes", "image/png")


# ---------------------------------------------------------------------------
# extract_text (dispatcher)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_text_routes_pdf_by_content_type():
    with patch("app.services.text_extraction.extract_text_from_pdf", new_callable=AsyncMock) as mock_pdf:
        mock_pdf.return_value = "PDF content"
        from app.services.text_extraction import extract_text
        text, status = await extract_text(b"bytes", "application/pdf", "doc.pdf")

    assert text == "PDF content"
    assert status == "success"


@pytest.mark.asyncio
async def test_extract_text_routes_pdf_by_filename():
    with patch("app.services.text_extraction.extract_text_from_pdf", new_callable=AsyncMock) as mock_pdf:
        mock_pdf.return_value = "PDF content"
        from app.services.text_extraction import extract_text
        text, status = await extract_text(b"bytes", "application/octet-stream", "resume.pdf")

    assert text == "PDF content"
    assert status == "success"


@pytest.mark.asyncio
async def test_extract_text_routes_docx():
    with patch("app.services.text_extraction.extract_text_from_docx", new_callable=AsyncMock) as mock_docx:
        mock_docx.return_value = "DOCX content"
        from app.services.text_extraction import extract_text
        text, status = await extract_text(b"bytes", "application/octet-stream", "resume.docx")

    assert text == "DOCX content"
    assert status == "success"


@pytest.mark.asyncio
async def test_extract_text_routes_image():
    with patch("app.services.text_extraction.extract_text_from_image", new_callable=AsyncMock) as mock_img:
        mock_img.return_value = "Image text found"
        from app.services.text_extraction import extract_text
        text, status = await extract_text(b"bytes", "image/png", "screenshot.png")

    assert text == "Image text found"
    assert status == "success"


@pytest.mark.asyncio
async def test_extract_text_plain_utf8():
    from app.services.text_extraction import extract_text
    text, status = await extract_text("hello world".encode("utf-8"), "text/plain", "note.txt")
    assert text == "hello world"
    assert status == "success"


@pytest.mark.asyncio
async def test_extract_text_unsupported_returns_unsupported():
    from app.services.text_extraction import extract_text
    text, status = await extract_text(b"bytes", "application/zip", "archive.zip")
    assert text == ""
    assert status == "unsupported"


@pytest.mark.asyncio
async def test_extract_text_exception_returns_failed():
    with patch("app.services.text_extraction.extract_text_from_pdf", new_callable=AsyncMock) as mock_pdf:
        mock_pdf.side_effect = Exception("disk error")
        from app.services.text_extraction import extract_text
        text, status = await extract_text(b"bytes", "application/pdf", "doc.pdf")

    assert text == ""
    assert status == "failed"


# ---------------------------------------------------------------------------
# extract_all_attachments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_all_attachments_combines_text():
    fake_bytes = b"fake pdf"
    b64 = base64.b64encode(fake_bytes).decode()

    with patch("app.services.text_extraction.extract_text", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = ("Doc text", "success")
        from app.services.text_extraction import extract_all_attachments
        combined, meta = await extract_all_attachments([
            {"filename": "a.pdf", "content_type": "application/pdf", "data": b64},
            {"filename": "b.pdf", "content_type": "application/pdf", "data": b64},
        ])

    assert "--- a.pdf ---" in combined
    assert "--- b.pdf ---" in combined
    assert len(meta) == 2
    assert all(m["extraction_status"] == "success" for m in meta)


@pytest.mark.asyncio
async def test_extract_all_attachments_handles_bad_base64():
    from app.services.text_extraction import extract_all_attachments
    combined, meta = await extract_all_attachments([
        {"filename": "bad.pdf", "content_type": "application/pdf", "data": "!!!not_base64!!!"},
    ])
    assert combined == ""
    assert meta[0]["extraction_status"] == "failed"
