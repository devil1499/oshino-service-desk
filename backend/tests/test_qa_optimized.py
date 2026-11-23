from app.modules.qa.graph import Question, Source, ask, build_graph

async def test_answer_uses_two_calls_and_compact_sources():
    calls = []
    source = Source(source_id="K1", document_id=1, chunk_id=1, title="登录", content="重置密码。", fingerprint="v1")
    async def search(query, product):
        return [source, source]
    async def model(prompt, data, schema):
        calls.append(data)
        if len(calls) == 1:
            return {"action": "search", "text": "密码错误"}
        assert data["sources"] == [{"source_id": "K1", "title": "登录", "content": "重置密码。"}]
        return {"action": "answer", "text": "依据充分", "paragraphs": [{"text": "重置密码。", "source_ids": ["K1"]}]}
    answer = await ask(build_graph(model, search), Question(text="密码错误", product_id=1, history=[]))
    assert answer.status == "answered"
    assert len(calls) == 2
    assert answer.sources == [source]
