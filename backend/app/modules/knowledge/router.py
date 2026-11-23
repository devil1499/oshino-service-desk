import asyncio
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

from fastapi import APIRouter, Form, HTTPException, Query, UploadFile
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AdminUser, CurrentUser, DbSession
from app.integrations import document_extract
from app.models import KnowledgeChunk, KnowledgeDocument
from app.modules.knowledge.schemas import DocumentInput, DocumentPage, DocumentView
from app.modules.knowledge.text import document_fingerprint, split_text
from app.modules.tickets.service import validate_catalog

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])


async def get_document(db: AsyncSession, document_id: int, *, lock: bool = False) -> KnowledgeDocument:
    query = select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
    if lock:
        query = query.with_for_update()
    document = await db.scalar(query)
    if document is None:
        raise HTTPException(404, "知识文档不存在")
    return document


@router.get("", response_model=DocumentPage)
async def list_documents(
    db: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    q: Annotated[str, Query(max_length=200)] = "",
    status: Literal["draft", "published", "disabled"] | None = None,
):
    filters = [] if user.role == "admin" else [KnowledgeDocument.status == "published"]
    keyword = q.strip()
    if keyword:
        filters.append(
            KnowledgeDocument.title.icontains(keyword, autoescape=True)
            | KnowledgeDocument.content.icontains(keyword, autoescape=True)
        )
    if status is not None:
        filters.append(KnowledgeDocument.status == status)
    total = await db.scalar(select(func.count()).select_from(KnowledgeDocument).where(*filters))
    items = (
        await db.scalars(
            select(KnowledgeDocument)
            .where(*filters)
            .order_by(KnowledgeDocument.id.desc())
            .offset((page - 1) * 20)
            .limit(20)
        )
    ).all()
    return {"items": items, "total": total, "page": page}


@router.post("", response_model=DocumentView, status_code=201)
async def create_document(body: DocumentInput, db: DbSession, user: AdminUser):
    await validate_catalog(db, body.product_id, body.module_id, body.category_id)
    document = KnowledgeDocument(**body.model_dump(), source_name="手工录入")
    db.add(document)
    await db.commit()
    return document


@router.post("/upload", response_model=DocumentView, status_code=201)
async def upload_document(
    file: UploadFile,
    title: Annotated[str, Form()],
    product_id: Annotated[int, Form(gt=0)],
    module_id: Annotated[int, Form(gt=0)],
    category_id: Annotated[int, Form(gt=0)],
    db: DbSession,
    user: AdminUser,
):
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".md", ".txt", ".pdf", ".jpg", ".jpeg", ".png"}:
        raise HTTPException(422, "只支持 MD、TXT、PDF、JPG 和 PNG 文件")
    await validate_catalog(db, product_id, module_id, category_id)
    limit = 256 * 1024 if suffix in {".md", ".txt"} else 10 * 1024 * 1024
    try:
        raw = await file.read(limit + 1)
    finally:
        await file.close()
    if len(raw) > limit:
        raise HTTPException(413, "文本不能超过 256 KiB，PDF 和图片不能超过 10 MiB")
    if suffix in {".md", ".txt"}:
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise HTTPException(422, "文档必须使用 UTF-8 编码") from error
    else:
        with TemporaryDirectory() as folder:
            source = Path(folder) / ("source" + suffix)
            source.write_bytes(raw)
            try:
                content = await asyncio.to_thread(document_extract.extract_file, source)
            except document_extract.ModelUnavailable as error:
                raise HTTPException(503, str(error)) from error
            except document_extract.ExtractionError as error:
                raise HTTPException(422, str(error)) from error
    # 上传和直接录入使用同一套边界规则；错误不包含正文。
    try:
        body = DocumentInput(
            title=title, content=content, product_id=product_id, module_id=module_id, category_id=category_id
        )
    except ValidationError as error:
        raise HTTPException(422, "标题须为1—200字，正文须为1—100000字") from error
    document = KnowledgeDocument(**body.model_dump(), source_name=filename.replace("\\", "/").split("/")[-1][:200])
    db.add(document)
    await db.commit()
    return document


@router.get("/{document_id}", response_model=DocumentView)
async def document_detail(document_id: int, db: DbSession, user: CurrentUser):
    document = await get_document(db, document_id)
    if user.role != "admin" and document.status != "published":
        raise HTTPException(403, "该知识文档尚未发布或已停用")
    return document


@router.put("/{document_id}/content", response_model=DocumentView)
async def update_content(document_id: int, body: DocumentInput, db: DbSession, user: AdminUser):
    document = await get_document(db, document_id, lock=True)
    await validate_catalog(db, body.product_id, body.module_id, body.category_id)
    for field, value in body.model_dump().items():
        setattr(document, field, value)
    document.revision += 1
    document.status = "draft"
    document.chunk_count = 0
    document.updated_at = datetime.now(UTC)
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
    await db.commit()
    return document


@router.post("/{document_id}/publish", response_model=DocumentView)
async def publish_document(document_id: int, db: DbSession, user: AdminUser):
    document = await get_document(db, document_id, lock=True)
    if document.status == "published":
        raise HTTPException(409, "文档已经发布；正文变更请先编辑")
    await validate_catalog(db, document.product_id, document.module_id, document.category_id)
    document.revision += 1
    document.status = "published"
    document.updated_at = datetime.now(UTC)
    chunks = split_text(document.content)
    fingerprint = document_fingerprint(document)
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
    db.add_all(
        [
            KnowledgeChunk(document_id=document.id, chunk_order=i + 1, content=text, fingerprint=fingerprint)
            for i, text in enumerate(chunks)
        ]
    )
    document.chunk_count = len(chunks)
    await db.commit()
    return document


@router.post("/{document_id}/disable", response_model=DocumentView)
async def disable_document(document_id: int, db: DbSession, user: AdminUser):
    document = await get_document(db, document_id, lock=True)
    document.status = "disabled"
    document.updated_at = datetime.now(UTC)
    await db.commit()
    return document
