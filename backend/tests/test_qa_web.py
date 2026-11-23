import json

import pytest

from app.integrations.web_search import WebSource
from app.modules.qa.graph import Question, ask, build_graph, InvalidCitation


@pytest.mark.parametrize("enabled", [False, True])
async def test_web_search_is_opt_in_and_citations_are_from_actual_results(enabled):
    searches = []

    async def knowledge(query, product_id):
        assert product_id == 7
        return []

    async def web(query):
        searches.append(query)
        return [
            WebSource(
                source_id="W1",
                title="官方文档",
                content="检查网络",
                url="https://docs.example.com",
                retrieved_at="2026-11-04T00:00:00Z",
            )
        ]

    async def model(instruction, data, result_type):
        json.dumps(data, ensure_ascii=False)  # 与真实聊天接口相同，来源必须能序列化。
        if result_type.__name__ == "Plan":
            return result_type(action="search", text="登录失败")
        if result_type.__name__ == "Assessment":
            return result_type(action="answer" if data["sources"] else "insufficient", text="资料判断", paragraphs=[{"text": "可检查网络。", "source_ids": ["W1"]}] if data["sources"] else [])
        return result_type(paragraphs=[{"text": "可检查网络。", "source_ids": ["W1"]}])

    answer = await ask(
        build_graph(model, knowledge, web_search=web),
        Question(text="登录失败", product_id=7, history=[], web_search=enabled),
    )
    assert len(searches) == (1 if enabled else 0)
    assert answer.status == ("answered" if enabled else "insufficient")
    if enabled:
        assert answer.sources[0].kind == "web"


async def test_invented_web_citations_are_rejected():
    async def knowledge(query, product_id):
        return []

    async def web(query):
        return [
            WebSource(
                source_id="W1",
                title="官方文档",
                content="检查网络",
                url="https://docs.example.com",
                retrieved_at="2026-11-04T00:00:00Z",
            )
        ]

    async def model(instruction, data, result_type):
        if result_type.__name__ == "Plan":
            return result_type(action="search", text="登录")
        if result_type.__name__ == "Assessment":
            return result_type(action="answer", text="有资料", paragraphs=[{"text": "结论", "source_ids": ["W99"]}])
        return result_type(paragraphs=[{"text": "结论", "source_ids": ["W99"]}])

    with pytest.raises(InvalidCitation):
        await ask(
            build_graph(model, knowledge, web_search=web),
            Question(text="登录", product_id=7, history=[], web_search=True),
        )
