import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.retrieval_settings import RetrievalSettings
from app.modules.analysis.router import get_retrieval_settings


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    monkeypatch.setitem(RetrievalSettings.model_config, "env_file", None)
    for name in RetrievalSettings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def test_missing_configuration_reports_fields_without_secrets(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "private-test-key")
    with pytest.raises(HTTPException) as caught:
        get_retrieval_settings()
    assert caught.value.status_code == 503
    assert "embedding_model" in caught.value.detail
    assert "private-test-key" not in caught.value.detail


@pytest.mark.parametrize(
    "changes",
    [
        {"milvus_db_path": "relative.db"},
        {"model_base_url": "https://user:password@example.com/v1"},
        {"model_base_url": "https://example.com/v1?key=private"},
        {"model_api_key": ""},
        {"embedding_dimensions": 0},
    ],
)
def test_invalid_retrieval_configuration_is_rejected(tmp_path, changes):
    values = dict(
        milvus_db_path=tmp_path / "cases.db",
        model_base_url="https://model.example/v1",
        model_api_key="test-only",
        embedding_model="fixture-model",
        embedding_dimensions=4,
    )
    with pytest.raises(ValidationError):
        RetrievalSettings.model_validate({**values, **changes})
