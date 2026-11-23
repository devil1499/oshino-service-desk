"""固定题集逐题运行与人工评阅；不把模型自评分当作准确率。"""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import func, select

from app.core.database import SessionFactoryDep
from app.core.security import CurrentUser, DbSession
from app.models import KnowledgeChunk, KnowledgeDocument, Product, QaConversation, QaEvaluationRun, QaMessage
from app.modules.analysis.assistance import ChatModel, EmbeddingModel
from app.modules.analysis.router import RetrievalConfig
from app.modules.knowledge.text import document_fingerprint
from app.modules.qa.evaluation_cases import DEMO_DOCUMENT_SUFFIX, REQUIRED_EVIDENCE, SUITE_VERSION, build_demo_cases
from app.modules.qa.graph import Message
from app.modules.qa.schemas import MessageInput
from app.modules.qa.service import send_question
from app.modules.qa.trace import redact

router = APIRouter(prefix='/api/qa/evaluations', tags=['回答评测'])
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class CaseInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    question: Text
    history: list[Message] = Field(default_factory=list, max_length=12)
    required_points: list[Text] = Field(min_length=1, max_length=20)
    expected_behavior: Literal['answered', 'clarification', 'insufficient']
    expected_chunk_ids: list[int] = Field(default_factory=list, max_length=10)
    forbidden: list[Text] = Field(default_factory=list, max_length=10)

    @model_validator(mode='after')
    def check_case(self):
        if self.expected_behavior == 'answered' and not self.expected_chunk_ids:
            raise ValueError('预期回答的题目必须指定参考知识块')
        if len(self.expected_chunk_ids) != len(set(self.expected_chunk_ids)):
            raise ValueError('参考知识块不能重复')
        if len(self.history) % 2 or any(message.role != ('user' if i % 2 == 0 else 'assistant') for i, message in enumerate(self.history)):
            raise ValueError('历史上下文必须按用户、助手组成完整轮次')
        if sum(len(message.content) for message in self.history) > 6000:
            raise ValueError('历史上下文不能超过6000字符')
        return self


class RunInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_id: int = Field(gt=0)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    cases: list[CaseInput] | None = Field(default=None, min_length=1, max_length=50)


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    correctness: Literal[0, 1, 2]
    covered_points: list[int] = Field(max_length=20)
    citation_support: Literal[0, 1, 2] | None
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize_results(results: list[dict]) -> dict:
    finished = [item for item in results if item['status'] not in {'running', 'failed', 'blocked'}]
    reviewed = [item for item in finished if item.get('review') is not None]
    retrieval = [item for item in finished if item.get('retrieval_recall') is not None]
    citation_reviews = [item for item in reviewed if item['review']['citation_support'] is not None]
    return {
        'finished': len(finished),
        'failed': sum(item['status'] in {'failed', 'blocked'} for item in results),
        'reviewed': len(reviewed),
        'correctness': average([item['review']['correctness'] / 2 for item in reviewed]),
        'completeness': average([len(item['review']['covered_points']) / item['point_count'] for item in reviewed]),
        'citation_support': average([item['review']['citation_support'] / 2 for item in citation_reviews]),
        'citation_samples': len(citation_reviews),
        'behavior_match': average([float(item['status'] == item['expected_behavior']) for item in finished]),
        'behavior_samples': len(finished),
        'retrieval_recall': average([item['retrieval_recall'] for item in retrieval]),
        'retrieval_hit': average([float(item['retrieval_hit']) for item in retrieval]),
        'retrieval_samples': len(retrieval),
    }


def run_view(run: QaEvaluationRun, *, include_cases: bool = True) -> dict:
    state = 'running' if run.active_case is not None else 'completed' if len(run.results) == len(run.cases) else 'ready'
    result = {
        'id': run.id, 'product_id': run.product_id, 'title': run.title, 'suite_version': run.suite_version,
        'created_at': run.created_at, 'state': state, 'case_count': len(run.cases),
        'suite_signature': hashlib.sha256(json.dumps(run.cases, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        'processed': len(run.results) - int(run.active_case is not None), 'metrics': summarize_results(run.results),
    }
    if include_cases:
        result.update(cases=run.cases, results=run.results)
    return result


async def owned_run(db, run_id: int, owner_id: int, *, lock: bool = False) -> QaEvaluationRun:
    query = select(QaEvaluationRun).where(QaEvaluationRun.id == run_id, QaEvaluationRun.owner_id == owner_id)
    run = await db.scalar(query.with_for_update() if lock else query)
    if run is None:
        raise HTTPException(404, '评测记录不存在')
    return run


async def published_scope(db, product_id: int) -> dict:
    documents = (await db.scalars(select(KnowledgeDocument).where(
        KnowledgeDocument.product_id == product_id, KnowledgeDocument.status == 'published',
    ).order_by(KnowledgeDocument.id))).all()
    return {str(doc.id): document_fingerprint(doc) for doc in documents}


@router.post('/runs', status_code=201)
async def create_run(body: RunInput, db: DbSession, user: CurrentUser):
    product = await db.get(Product, body.product_id)
    if product is None or not product.is_active:
        raise HTTPException(422, '请选择启用的产品')
    scope = await published_scope(db, body.product_id)
    if body.cases is None:
        docs = (await db.scalars(select(KnowledgeDocument).where(
            KnowledgeDocument.product_id == body.product_id, KnowledgeDocument.status == 'published',
        ))).all()
        if len(docs) != 1 or not docs[0].title.endswith(DEMO_DOCUMENT_SUFFIX) or not all(text in docs[0].content for text in REQUIRED_EVIDENCE):
            raise HTTPException(422, '内置30题仅适用于只发布了标准耳机演示规则的产品；其他产品请上传自定义题集')
        doc = docs[0]
        chunks = (await db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))).all()
        if not chunks:
            raise HTTPException(409, '演示规则尚未生成知识块，请重新发布文档')
        cases = build_demo_cases(doc.id, [chunk.id for chunk in chunks], scope[str(doc.id)])
        version = SUITE_VERSION
    else:
        cases = [case.model_dump() for case in body.cases]
        if len({case['id'] for case in cases}) != len(cases):
            raise HTTPException(422, '题目编号不能重复')
        version = 'custom-v1'
    for case in cases:
        case['knowledge_scope'] = scope
        references = []
        for chunk_id in case['expected_chunk_ids']:
            chunk = await db.get(KnowledgeChunk, chunk_id)
            document = await db.get(KnowledgeDocument, chunk.document_id) if chunk else None
            if document is None or str(document.id) not in scope or chunk.fingerprint != scope[str(document.id)]:
                raise HTTPException(422, f"题目 {case['id']} 的参考知识块不存在、跨产品或已失效")
            references.append({
                'source_id': f'K{chunk.id}', 'document_id': document.id, 'chunk_id': chunk.id,
                'title': document.title, 'content': chunk.content, 'fingerprint': chunk.fingerprint,
            })
        case['references'] = references
    run = QaEvaluationRun(owner_id=user.id, product_id=body.product_id, title=redact(body.title),
                          suite_version=version, cases=redact(cases), results=[], active_case=None)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run_view(run)


@router.get('/references')
async def list_references(product_id: int, db: DbSession, user: CurrentUser,
                          page: Annotated[int, Query(ge=1)] = 1):
    rows = (await db.execute(select(KnowledgeChunk, KnowledgeDocument).join(KnowledgeDocument).where(
        KnowledgeDocument.product_id == product_id, KnowledgeDocument.status == 'published',
    ).order_by(KnowledgeChunk.id).offset((page - 1) * 50).limit(51))).all()
    sources = []
    for chunk, document in rows[:50]:
        if chunk.fingerprint != document_fingerprint(document):
            raise HTTPException(409, '知识分块与文档版本不一致，请重新发布')
        sources.append({'source_id': f'K{chunk.id}', 'chunk_id': chunk.id, 'document_id': document.id,
                        'title': document.title, 'content': chunk.content, 'fingerprint': chunk.fingerprint})
    return {'items': redact(sources), 'page': page, 'has_more': len(rows) > 50}


@router.get('/runs')
async def list_runs(db: DbSession, user: CurrentUser, page: Annotated[int, Query(ge=1)] = 1):
    query = select(QaEvaluationRun).where(QaEvaluationRun.owner_id == user.id)
    count = await db.scalar(select(func.count()).select_from(QaEvaluationRun).where(QaEvaluationRun.owner_id == user.id))
    rows = (await db.scalars(query.order_by(QaEvaluationRun.id.desc()).offset((page - 1) * 20).limit(20))).all()
    return {'items': [run_view(run, include_cases=False) for run in rows], 'total': count, 'page': page}


@router.get('/runs/{run_id}')
async def get_run(run_id: int, db: DbSession, user: CurrentUser):
    return run_view(await owned_run(db, run_id, user.id))


def empty_result(case: dict, index: int, conversation_id: int | None) -> dict:
    return {
        'case_index': index, 'case_id': case['id'], 'conversation_id': conversation_id, 'message_id': None,
        'expected_behavior': case['expected_behavior'], 'status': 'running', 'answer': '', 'sources': [],
        'duration_ms': None, 'token_usage': None, 'error': None, 'review': None,
        'retrieval_recall': None, 'retrieval_hit': None, 'point_count': len(case['required_points']),
    }


async def execute_case(factory, run_id, index, conversation_id, owner_id, case, config, embedding, chat):
    error = None
    request_id = uuid4()
    try:
        await send_question(factory, conversation_id, owner_id,
                            MessageInput(request_id=request_id, text=case['question']), config, embedding, chat)
    except HTTPException as failure:
        error = str(failure.detail)
    except asyncio.CancelledError:
        await asyncio.shield(finish_result(factory, run_id, index, conversation_id, str(request_id), '评测请求中断'))
        raise
    except Exception:
        await finish_result(factory, run_id, index, conversation_id, str(request_id), '评测执行失败，请检查运行记录')
        raise
    await finish_result(factory, run_id, index, conversation_id, str(request_id), error)


async def finish_result(factory, run_id, index, conversation_id, request_id, error):
    async with factory.begin() as db:
        run = await db.scalar(select(QaEvaluationRun).where(QaEvaluationRun.id == run_id).with_for_update())
        if run.active_case != index:
            return
        result = dict(run.results[index])
        message = await db.scalar(select(QaMessage).where(
            QaMessage.conversation_id == conversation_id, QaMessage.request_id == request_id, QaMessage.role == 'assistant',
        ))
        if message is None:
            result.update(status='failed', error=error or '未生成问答运行记录')
        else:
            result.update(message_id=message.id, status=message.status, answer=message.content,
                          sources=message.sources, duration_ms=message.duration_ms, error=error)
            trace = message.run_details
            if trace:
                result['token_usage'] = trace.get('usage', {}).get('chat')
                expected = set(run.cases[index]['expected_chunk_ids'])
                if expected and message.status != 'failed':
                    retrieved = {source['chunk_id'] for step in trace['steps']
                                 if step['name'] == 'retrieve' and step['status'] == 'succeeded'
                                 for source in step['output']['sources']}
                    result['retrieval_recall'] = len(expected & retrieved) / len(expected)
                    result['retrieval_hit'] = bool(expected & retrieved)
        if result['status'] == 'running':
            result.update(status='failed', error=error or '评测请求中断')
        if await published_scope(db, run.product_id) != run.cases[index]['knowledge_scope']:
            result.update(status='blocked', error='执行期间知识版本已改变，本题不可用于比较',
                          retrieval_recall=None, retrieval_hit=None)
        results = list(run.results)
        results[index] = redact(result)
        run.results = results
        run.active_case = None


@router.post('/runs/{run_id}/next')
async def next_case(run_id: int, db: DbSession, user: CurrentUser, factory: SessionFactoryDep,
                    config: RetrievalConfig, embedding: EmbeddingModel, chat: ChatModel):
    owner_id = user.id
    await db.rollback()
    async with factory.begin() as session:
        run = await owned_run(session, run_id, owner_id, lock=True)
        if run.active_case is not None:
            raise HTTPException(409, '已有题目正在执行，请等待结果或刷新查看')
        index = len(run.results)
        if index == len(run.cases):
            return run_view(run)
        case = run.cases[index]
        product = await session.get(Product, run.product_id)
        if product is None or not product.is_active or await published_scope(session, run.product_id) != case['knowledge_scope']:
            raise HTTPException(409, '产品或知识版本已改变，本批评测不能继续；请基于新版本创建评测')
        conversation = QaConversation(owner_id=owner_id, product_id=run.product_id,
                                      title=f'评测 {run.id} · {case["id"]}', is_evaluation=True)
        session.add(conversation)
        await session.flush()
        # 多轮测试上下文是题集的明确前提，并非模型本轮自行生成的历史答案。
        for offset in range(0, len(case['history']), 2):
            context_id = str(uuid4())
            for message in case['history'][offset:offset + 2]:
                session.add(QaMessage(conversation_id=conversation.id, request_id=context_id,
                                      role=message['role'], content=message['content'], sources=[],
                                      status='submitted' if message['role'] == 'user' else 'answered'))
        run.active_case = index
        run.results = [*run.results, empty_result(case, index, conversation.id)]
        conversation_id = conversation.id
    await execute_case(factory, run_id, index, conversation_id, owner_id, case, config, embedding, chat)
    async with factory() as session:
        return run_view(await owned_run(session, run_id, owner_id))


@router.put('/runs/{run_id}/reviews/{case_index}')
async def review_case(run_id: int, case_index: int, body: ReviewInput, db: DbSession, user: CurrentUser):
    run = await owned_run(db, run_id, user.id, lock=True)
    if case_index < 0 or case_index >= len(run.results):
        raise HTTPException(404, '题目尚未执行')
    result = dict(run.results[case_index])
    if result['status'] in {'running', 'failed', 'blocked'}:
        raise HTTPException(409, '仅可评阅已正常完成的回答')
    if len(set(body.covered_points)) != len(body.covered_points) or any(i < 0 or i >= result['point_count'] for i in body.covered_points):
        raise HTTPException(422, '已覆盖要点编号不合法或重复')
    if not result['sources'] and body.citation_support is not None:
        raise HTTPException(422, '本题没有引用，请将引用支持度设为不适用')
    result['review'] = {**redact(body.model_dump()), 'reviewer_id': user.id, 'reviewed_at': datetime.now(UTC).isoformat()}
    results = list(run.results)
    results[case_index] = result
    run.results = results
    await db.commit()
    return run_view(run)


async def interrupt_evaluations(factory):
    async with factory.begin() as db:
        runs = (await db.scalars(select(QaEvaluationRun).where(QaEvaluationRun.active_case.is_not(None)).with_for_update())).all()
        for run in runs:
            index = run.active_case
            results = list(run.results)
            results[index] = {**results[index], 'status': 'failed', 'error': '服务重启中断评测，请在新批次重测此题'}
            run.results = results
            run.active_case = None
