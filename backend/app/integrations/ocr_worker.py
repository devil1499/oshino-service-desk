"""独立进程内解析 PDF/图片，入口只接收本机临时文件。"""

import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory


class ExtractionError(RuntimeError):
    pass


class ModelUnavailable(ExtractionError):
    pass


@lru_cache(maxsize=1)
def get_ocr():
    from pydantic import ValidationError

    from app.core.ocr_settings import OcrSettings

    try:
        config = OcrSettings.model_validate({})
    except ValidationError as error:
        raise ModelUnavailable(
            "OCR 本地模型配置无效，请检查 backend/.env.ocr 中的模型目录"
        ) from error
    try:
        from paddleocr import PaddleOCR

        return PaddleOCR(
            device="cpu",
            # 当前 PaddlePaddle 3.3.1 的 oneDNN 推理会报 PIR 属性转换错误。
            enable_mkldnn=False,
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="PP-OCRv5_mobile_rec",
            text_detection_model_dir=str(config.ocr_detection_model_dir),
            text_recognition_model_dir=str(config.ocr_recognition_model_dir),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            cpu_threads=2,
        )
    except (ImportError, RuntimeError, ValueError, OSError) as error:
        raise ModelUnavailable("OCR 引擎初始化失败，请检查 CPU 依赖与本地模型文件") from error


def recognize(path: Path) -> str:
    try:
        results = get_ocr().predict(str(path))
        return "\n".join(text for result in results for text in result["rec_texts"]).strip()
    except (RuntimeError, ValueError, OSError) as error:
        if isinstance(error, ExtractionError):
            raise
        raise ExtractionError("OCR 识别失败，请检查模型文件及输入图片") from error


def extract_content(path: Path) -> str:
    import pymupdf
    from PIL import Image, UnidentifiedImageError

    if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        try:
            with Image.open(path) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise ExtractionError("文件内容不是 JPG 或 PNG")
                if image.width * image.height > 16000000:
                    raise ExtractionError("图片不能超过 1600 万像素")
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise ExtractionError("图片损坏、格式不正确或尺寸过大") from error
        content = recognize(path)
    else:
        texts = []
        try:
            with pymupdf.open(path) as document, TemporaryDirectory(dir=path.parent) as temp:
                if not document.is_pdf or document.needs_pass:
                    raise ExtractionError("仅支持未加密的 PDF")
                if not 1 <= len(document) <= 20:
                    raise ExtractionError("PDF 必须为 1—20 页")
                for index in range(len(document)):
                    page = document.load_page(index)
                    page_text = page.get_text("text", sort=True)
                    assert isinstance(page_text, str)
                    text = page_text.strip()
                    if not text:
                        rect = page.rect
                        if not 0 < rect.width <= 2000 or not 0 < rect.height <= 2000:
                            raise ExtractionError("PDF 页面尺寸超出支持范围")
                        scale = min(150 / 72, 4000 / max(rect.width, rect.height))
                        image_path = Path(temp) / f"page-{index + 1}.png"
                        page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).save(
                            image_path
                        )
                        text = recognize(image_path)
                    if text:
                        texts.append(f"第{index + 1}页\n{text}")
                    if sum(len(item) for item in texts) > 100000:
                        raise ExtractionError("提取正文不能超过 100000 字")
        except (pymupdf.FileDataError, pymupdf.EmptyFileError) as error:
            raise ExtractionError("PDF 损坏或内容为空") from error
        content = "\n\n".join(texts)
    if not content.strip():
        raise ExtractionError("未提取到有效文字，请换用清晰资料或手工录入")
    if len(content) > 100000:
        raise ExtractionError("提取正文不能超过 100000 字")
    return content


def main():
    source, output = map(Path, sys.argv[1:3])
    try:
        # 原生库输出留在子进程中，不混入协议，也不打印文档正文。
        with open("/dev/null", "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
            content = extract_content(source)
        result = {"content": content}
    except ModelUnavailable as error:
        result = {"error": str(error), "kind": "model_unavailable"}
    except ExtractionError as error:
        result = {"error": str(error)}
    output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
