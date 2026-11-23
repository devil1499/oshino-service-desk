from fastapi import APIRouter, HTTPException

from app.core.security import CurrentUser
from app.integrations.case_index import CaseIndex
from app.integrations.hybrid_index import IndexNotReady
from app.integrations.knowledge_index import KnowledgeIndex
from app.modules.analysis.router import RetrievalConfig

router = APIRouter(prefix="/api/evaluation", tags=["评测配置"])


@router.get("/config")
def evaluation_config(user: CurrentUser, config: RetrievalConfig):
    try:
        with CaseIndex(
            config.milvus_db_path, config.embedding_model, str(config.model_base_url), config.embedding_dimensions
        ) as cases:
            case_metadata = cases.ready()
        with KnowledgeIndex(
            config.milvus_db_path, config.embedding_model, str(config.model_base_url), config.embedding_dimensions
        ) as knowledge:
            knowledge_metadata = knowledge.ready()
    except IndexNotReady as error:
        raise HTTPException(503, str(error)) from error
    return {
        "cases": case_metadata,
        "knowledge": knowledge_metadata,
        "per_channel_candidates": 20,
        "rrf_k": 60,
        "max_results": 5,
        "scope_policy": "module_then_category",
        "chunk_size": 500,
        "chunk_overlap": 80,
    }
