"""只在 WSL 手动执行，用于提前下载 OCR 模型，不在 Web 请求中联网下载。"""

from pathlib import Path

from paddleocr import PaddleOCR

if __name__ == "__main__":
    PaddleOCR(
        device="cpu",
        enable_mkldnn=False,
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        cpu_threads=2,
    )
    cache = Path.home() / ".paddlex" / "official_models"
    for key, name in [
        ("OCR_DETECTION_MODEL_DIR", "PP-OCRv5_mobile_det"),
        ("OCR_RECOGNITION_MODEL_DIR", "PP-OCRv5_mobile_rec"),
    ]:
        directory = cache / name
        if not directory.is_dir():
            raise RuntimeError(
                f"未找到下载后的模型目录：{directory}，请根据 PaddleOCR 输出确认实际位置"
            )
        print(f"{key}={directory}")
