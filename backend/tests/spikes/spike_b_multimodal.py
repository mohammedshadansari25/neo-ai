import base64
import io
import time

import pymupdf
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field

from app.config import get_settings

Image.MAX_IMAGE_PIXELS = 4096 * 4096


class SpikeBExtraction(BaseModel):
    extracted_text: str = Field(min_length=1)
    dates: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


def _build_test_png_bytes() -> bytes:
    img = Image.new("RGB", (400, 120), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 40), "DBMS Exam: 2026-12-14", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_test_pdf_bytes(png_bytes: bytes) -> bytes:
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Page 1: Neo AI V1 Spike B selectable text content for validation.")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Page 2: Project milestone review scheduled for 2026-12-10.")
    p3 = doc.new_page()
    p3.insert_image(pymupdf.Rect(50, 50, 350, 170), stream=png_bytes)
    return doc.tobytes()


def test_spike_b_multimodal_pdf_and_image_pipeline():
    """
    Spike B: Prove magic-byte validation, Pillow pixel cap/re-encode,
    PyMuPDF page extraction + 150 DPI scanned-page PNG fallback, and
    Pydantic v2 structured output (plus live Vision API if key is set).
    """
    settings = get_settings()
    png_bytes = _build_test_png_bytes()
    pdf_bytes = _build_test_pdf_bytes(png_bytes)

    # 1. Magic-byte validation
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n"), "PNG magic bytes invalid"
    assert pdf_bytes.startswith(b"%PDF-"), "PDF magic bytes invalid"
    assert len(png_bytes) <= settings.MAX_IMAGE_BYTES
    assert len(pdf_bytes) <= settings.MAX_PDF_BYTES

    # 2. Pillow safe decode & re-encode
    with Image.open(io.BytesIO(png_bytes)) as img:
        w, h = img.size
        assert w * h <= Image.MAX_IMAGE_PIXELS
        reencoded = io.BytesIO()
        img.convert("RGB").save(reencoded, format="PNG")
        clean_png = reencoded.getvalue()
        assert len(clean_png) > 0

    # 3. PyMuPDF page-by-page extraction with <50 char scanned fallback at 150 DPI
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    assert doc.page_count == 3
    assert doc.page_count <= settings.MAX_PDF_PAGES

    extracted_pages: list[dict[str, object]] = []
    scanned_pngs: list[bytes] = []
    for idx in range(doc.page_count):
        page = doc.load_page(idx)
        page_text = page.get_text("text").strip()
        if len(page_text) < 50:
            pix = page.get_pixmap(dpi=150)
            scanned_pngs.append(pix.tobytes("png"))
            extracted_pages.append({"page": idx + 1, "mode": "vision_fallback", "text": page_text})
        else:
            extracted_pages.append({"page": idx + 1, "mode": "text", "text": page_text})

    assert extracted_pages[0]["mode"] == "text"
    assert extracted_pages[1]["mode"] == "text"
    assert extracted_pages[2]["mode"] == "vision_fallback"
    assert len(scanned_pngs) == 1

    # 4. Pydantic v2 validation + optional live Vision API check
    if settings.OPENAI_API_KEY != "sk-placeholder" and settings.OPENAI_API_KEY.strip():
        from openai import OpenAI

        client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=30.0)
        b64 = base64.b64encode(clean_png).decode("ascii")
        t0 = time.perf_counter()
        resp = client.beta.chat.completions.parse(
            model=settings.VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract text, ISO dates, and action items from this image."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
            response_format=SpikeBExtraction,
        )
        elapsed = time.perf_counter() - t0
        parsed = resp.choices[0].message.parsed
        assert isinstance(parsed, SpikeBExtraction)
        assert elapsed < 30.0, f"Vision API took {elapsed:.2f}s"
    else:
        # Validate schema contract locally when API key is still placeholder
        sample = SpikeBExtraction(
            extracted_text="DBMS Exam: 2026-12-14",
            dates=["2026-12-14"],
            action_items=["Prepare for DBMS Exam"],
            confidence=0.95,
        )
        assert sample.confidence >= 0.75
