from app.modules.qa.evaluation_cases import DEFAULT_CASES, build_demo_cases
import pytest
from test_qa_api import qa as qa
from test_similar import retrieval as retrieval
from test_postgres_foundation import database as database, TEST_PASSWORD


def test_demo_suite_has_30_distinct_questions_and_explicit_references():
    cases = build_demo_cases(7, [11], '知识指纹')
    assert len(cases) == 30
    assert len({item['question'] for item in cases}) == 30
    assert {item['expected_behavior'] for item in cases} == {'answered', 'clarification', 'insufficient'}
    answered = [item for item in cases if item['expected_behavior'] == 'answered']
    assert all(item['required_points'] and item['expected_chunk_ids'] == [11] for item in answered)
    assert all(item['history'] for item in cases if item['category'] == '多轮追问')
    assert len(DEFAULT_CASES) == 30


def test_summary_separates_manual_grades_from_behavior_and_retrieval():
    from app.modules.qa.evaluation import summarize_results
    results = [
        {'status': 'answered', 'expected_behavior': 'answered', 'retrieval_recall': 0.5,
         'retrieval_hit': True, 'review': {'correctness': 2, 'covered_points': [0], 'citation_support': 1}, 'point_count': 2},
        {'status': 'insufficient', 'expected_behavior': 'answered', 'retrieval_recall': None,
         'retrieval_hit': None, 'review': None, 'point_count': 2},
        {'status': 'failed', 'expected_behavior': 'answered', 'retrieval_recall': None,
         'retrieval_hit': None, 'review': None, 'point_count': 2},
    ]
    metrics = summarize_results(results)
    assert metrics['reviewed'] == 1
    assert metrics['correctness'] == 1
    assert metrics['completeness'] == 0.5
    assert metrics['citation_support'] == 0.5
    assert metrics['behavior_match'] == 0.5
    assert metrics['retrieval_recall'] == 0.5
    assert metrics['retrieval_samples'] == 1
    assert metrics['failed'] == 1
    assert summarize_results([])['correctness'] is None


@pytest.mark.postgres
async def test_evaluation_records_real_pipeline_and_manual_review_without_cross_owner_access(qa):
    app, client, headers, catalog, document, calls = qa
    references = (await client.get(f'/api/qa/evaluations/references?product_id={catalog["product_id"]}', headers=headers)).json()
    chunk_id = references['items'][0]['chunk_id']
    case = {'id': 'login-1', 'category': '正常问题', 'question': '登录E401怎么处理？',
            'required_points': ['检查角色绑定', '验证登录'], 'expected_behavior': 'answered',
            'expected_chunk_ids': [chunk_id], 'forbidden': ['索取密码']}
    created = await client.post('/api/qa/evaluations/runs', headers=headers,
                                json={'product_id': catalog['product_id'], 'title': '固定题集验收', 'cases': [case]})
    assert created.status_code == 201, created.text
    run_id = created.json()['id']
    assert created.json()['metrics']['correctness'] is None
    finished = await client.post(f'/api/qa/evaluations/runs/{run_id}/next', headers=headers)
    assert finished.status_code == 200, finished.text
    run = finished.json()
    assert run['state'] == 'completed'
    assert run['results'][0]['status'] == 'answered'
    assert run['results'][0]['message_id'] is not None
    assert run['metrics']['correctness'] is None
    assert run['metrics']['retrieval_hit'] == 1
    assert len(calls) == 3
    again = await client.post(f'/api/qa/evaluations/runs/{run_id}/next', headers=headers)
    assert again.json()['results'] == run['results']
    assert len(calls) == 3
    conversations = (await client.get('/api/qa/conversations', headers=headers)).json()['items']
    assert not any(item['id'] == run['results'][0]['conversation_id'] for item in conversations)
    review = {'correctness': 2, 'covered_points': [0], 'citation_support': 2, 'note': '正确，但缺少验证登录步骤'}
    reviewed = await client.put(f'/api/qa/evaluations/runs/{run_id}/reviews/0', headers=headers, json=review)
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()['metrics']['completeness'] == 0.5
    assert reviewed.json()['metrics']['correctness'] == 1
    invalid = await client.put(f'/api/qa/evaluations/runs/{run_id}/reviews/0', headers=headers,
                               json={**review, 'covered_points': [0, 0]})
    assert invalid.status_code == 422
    await client.post('/api/users', headers=headers, json={'username': 'eval_staff', 'display_name': '客服', 'password': TEST_PASSWORD})
    login = await client.post('/api/auth/login', json={'username': 'eval_staff', 'password': TEST_PASSWORD})
    staff = {'Authorization': 'Bearer ' + login.json()['access_token']}
    assert (await client.get(f'/api/qa/evaluations/runs/{run_id}', headers=staff)).status_code == 404
    assert (await client.put(f'/api/qa/evaluations/runs/{run_id}/reviews/0', headers=staff, json=review)).status_code == 404


@pytest.mark.postgres
async def test_changed_knowledge_stops_evaluation_before_model_call(qa):
    app, client, headers, catalog, document, calls = qa
    references = (await client.get(f'/api/qa/evaluations/references?product_id={catalog["product_id"]}', headers=headers)).json()
    case = {'id': 'version-1', 'category': '正常问题', 'question': '登录E401怎么办？',
            'required_points': ['检查角色绑定'], 'expected_behavior': 'answered',
            'expected_chunk_ids': [references['items'][0]['chunk_id']]}
    run = (await client.post('/api/qa/evaluations/runs', headers=headers,
                            json={'product_id': catalog['product_id'], 'title': '版本测试', 'cases': [case]})).json()
    disabled = await client.post(f'/api/knowledge/{document["id"]}/disable', headers=headers)
    assert disabled.status_code == 200, disabled.text
    changed = await client.post(f'/api/qa/evaluations/runs/{run["id"]}/next', headers=headers)
    assert changed.status_code == 409
    assert len(calls) == 0
