from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OcrSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env.ocr",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )
    ocr_detection_model_dir: Path
    ocr_recognition_model_dir: Path

    @field_validator("ocr_detection_model_dir", "ocr_recognition_model_dir")
    @classmethod
    def local_directory(cls, value: Path) -> Path:
        if not value.is_absolute() or not value.is_dir():
            raise ValueError("须填写存在的 WSL 绝对模型目录")
        return value
