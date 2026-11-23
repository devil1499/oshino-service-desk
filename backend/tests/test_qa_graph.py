import unittest

from app.modules.qa.graph import Assessment, Draft, Plan, Question, Source, ask, build_graph

SOURCE = Source(source_id='K1', document_id=1, chunk_id=1, title='登录指南',
                content='检查角色绑定。', fingerprint='revision-1')


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def run_flow(self, outputs, hits=None, history=None):
        calls = []
        async def model(prompt, data, schema):
            return schema.model_validate(outputs.pop(0))
        async def search(query, product):
            calls.append((query, product))
            return [SOURCE] if hits is None else hits
        answer = await ask(build_graph(model, search), Question(text='怎么解决？', product_id=7, history=history or []))
        return answer, calls

    async def test_answer_has_real_citations(self):
        answer, calls = await self.run_flow([
            {'action': 'search', 'text': '登录 E401'},
            {'action': 'answer', 'text': '依据充分', 'paragraphs': [{'text': '检查角色绑定。', 'source_ids': ['K1']}]},
        ])
        self.assertEqual(answer.status, 'answered')
        self.assertEqual(answer.sources, [SOURCE])
        self.assertEqual(calls, [('登录 E401', 7)])

    async def test_clarification_does_not_search(self):
        answer, calls = await self.run_flow([{'action': 'clarify', 'text': '出现什么错误码？'}])
        self.assertEqual(answer.status, 'clarification')
        self.assertEqual(calls, [])

    async def test_rewrite_has_two_search_limit(self):
        answer, calls = await self.run_flow([
            {'action': 'search', 'text': '登录失败'},
            {'action': 'rewrite', 'text': '角色绑定'},
            {'action': 'rewrite', 'text': '继续查询'},
        ], hits=[])
        self.assertEqual(len(calls), 2)
        self.assertEqual(answer.status, 'insufficient')

    async def test_empty_sources_cannot_produce_answer(self):
        answer, _ = await self.run_flow([
            {'action': 'search', 'text': '登录失败'}, {'action': 'answer', 'text': '错误地认为有依据'},
        ], hits=[])
        self.assertEqual(answer.status, 'insufficient')

    async def test_unknown_citation_rejected(self):
        with self.assertRaisesRegex(ValueError, '来源'):
            await self.run_flow([
                {'action': 'search', 'text': '登录失败'}, {'action': 'answer', 'text': '有依据', 'paragraphs': [{'text': '检查设置', 'source_ids': ['K999']}]},
            ])

    async def test_search_failure_is_not_insufficient_answer(self):
        async def model(prompt, data, schema):
            return Plan(action='search', text='登录失败')
        async def search(query, product):
            raise ConnectionError('索引连接失败')
        with self.assertRaises(ConnectionError):
            await ask(build_graph(model, search), Question(text='问题', product_id=1, history=[]))

    async def test_history_passed_to_planner(self):
        seen = []
        async def model(prompt, data, schema):
            seen.append(data)
            return Plan(action='clarify', text='请提供截图中的错误码')
        async def search(query, product):
            self.fail('澄清分支不应检索')
        await ask(build_graph(model, search), Question(text='下一步呢？', product_id=1,
            history=[{'role':'user','content':'我无法登录'}]))
        self.assertEqual(seen[0]['history'][0]['content'], '我无法登录')

    async def test_followup_keeps_meaning_after_search_rewrite(self):
        resolved_question = '登录 E401 处理步骤中的第二步角色绑定在哪里设置？'
        calls = []
        assessments = 0

        async def model(prompt, data, schema):
            nonlocal assessments
            if schema is Plan:
                self.assertEqual(data['history'][0]['content'], '第二步是检查角色绑定。')
                return Plan(action='search', text=resolved_question)
            self.assertEqual(data['resolved_question'], resolved_question)
            if schema is Assessment:
                assessments += 1
                if assessments == 1:
                    return Assessment(action='rewrite', text='角色绑定 设置入口')
                return Assessment(action='answer', text='第二次检索找到了入口', paragraphs=[{'text': '进入账号设置检查角色绑定。', 'source_ids': ['K1']}])
            self.assertIs(schema, Draft)
            self.assertEqual(data['query'], '角色绑定 设置入口')
            return Draft(paragraphs=[{'text': '进入账号设置检查角色绑定。', 'source_ids': ['K1']}])

        async def search(query, product):
            calls.append((query, product))
            return [] if len(calls) == 1 else [SOURCE]

        answer = await ask(build_graph(model, search), Question(
            text='第二步在哪里设置？', product_id=7,
            history=[{'role': 'assistant', 'content': '第二步是检查角色绑定。'}],
        ))
        self.assertEqual(answer.status, 'answered')
        self.assertEqual(calls, [(resolved_question, 7), ('角色绑定 设置入口', 7)])


if __name__ == '__main__':
    unittest.main()
