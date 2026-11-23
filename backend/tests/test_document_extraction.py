from io import BytesIO

import pymupdf
import pytest
from PIL import Image
from test_postgres_foundation import database as database
from test_tickets import ticket_context as ticket_context

from app.integrations import document_extract, ocr_worker


def test_text_pdf_uses_text_layer_without_ocr(tmp_path, monkeypatch):
    source = tmp_path / "manual.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((40, 60), "E401 login guide")
    document.save(source)
    document.close()
    monkeypatch.setattr(ocr_worker, "recognize", lambda path: pytest.fail("text PDF must not use OCR"))

    assert "E401 login guide" in ocr_worker.extract_content(source)


def test_text_pdf_passes_through_worker_process(tmp_path):
    source = tmp_path / "guide.pdf"
    document = pymupdf.open()
    document.new_page().insert_text((40, 60), "E401 login guide")
    document.save(source)
    document.close()

    assert "E401 login guide" in document_extract.extract_file(source)


def test_image_is_checked_before_mock_ocr(tmp_path, monkeypatch):
    source = tmp_path / "scan.png"
    Image.new("RGB", (80, 40), "white").save(source)
    monkeypatch.setattr(ocr_worker, "recognize", lambda path: "模拟识别的说明文字")

    assert ocr_worker.extract_content(source) == "模拟识别的说明文字"
    source.write_bytes(b"not an image")
    with pytest.raises(ocr_worker.ExtractionError, match="图片损坏"):
        ocr_worker.extract_content(source)


@pytest.mark.postgres
async def test_image_upload_creates_a_draft_for_admin_review(ticket_context, monkeypatch):
    client, headers, catalog = ticket_context
    monkeypatch.setattr(document_extract, "extract_file", lambda path: "识别出的登录排查知识", raising=False)
    metadata = {key: catalog[key] for key in ("product_id", "module_id", "category_id")}
    response = await client.post(
        "/api/knowledge/upload", headers=headers,
        data={**metadata, "title": "扫描说明"},
        files={"file": ("说明.png", b"fake-image-handled-by-test-extractor", "image/png")},
    )
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["status"] == "draft"
    assert document["chunk_count"] == 0
    assert document["content"] == "识别出的登录排查知识"


@pytest.mark.postgres
async def test_missing_ocr_model_keeps_knowledge_list_empty(ticket_context, monkeypatch):
    client, headers, catalog = ticket_context
    monkeypatch.setenv("OCR_DETECTION_MODEL_DIR", "/missing/ocr-det")
    monkeypatch.setenv("OCR_RECOGNITION_MODEL_DIR", "/missing/ocr-rec")
    image = BytesIO()
    Image.new("RGB", (80, 40), "white").save(image, format="PNG")
    metadata = {key: catalog[key] for key in ("product_id", "module_id", "category_id")}

    response = await client.post(
        "/api/knowledge/upload", headers=headers,
        data={**metadata, "title": "缺少模型的扫描件"},
        files={"file": ("说明.png", image.getvalue(), "image/png")},
    )
    assert response.status_code == 503, response.text
    assert (await client.get("/api/knowledge", headers=headers)).json()["total"] == 0
