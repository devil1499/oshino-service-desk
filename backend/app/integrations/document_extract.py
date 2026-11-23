import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore

from app.integrations.ocr_worker import ExtractionError, ModelUnavailable

slot = BoundedSemaphore(1)


def extract_file(path: Path) -> str:
    if not slot.acquire(blocking=False):
        raise ExtractionError("当前有资料正在识别，请完成后再上传")
    try:
        with TemporaryDirectory() as temp:
            output = Path(temp) / "result.json"
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "app.integrations.ocr_worker", str(path), str(output)],
                    cwd=Path(__file__).resolve().parents[2],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=180,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise ExtractionError(
                    "资料识别超过 180 秒，进程已终止；请拆分文件后再试"
                ) from error
            if completed.returncode != 0 or not output.exists():
                raise ExtractionError("资料解析进程失败，请检查已安装的 PDF/OCR 依赖")
            result = json.loads(output.read_text(encoding="utf-8"))
            if "error" in result:
                if result.get("kind") == "model_unavailable":
                    raise ModelUnavailable(result["error"])
                raise ExtractionError(result["error"])
            return result["content"]
    finally:
        slot.release()
