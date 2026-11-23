"""用项目真实解析器检查导入格式，不连接数据库。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2] / 'backend'))
from app.modules.tickets.import_csv import MAX_BYTES, parse_csv

content = (ROOT / '工单2000条.csv').read_bytes()
assert len(content) <= MAX_BYTES
rows = parse_csv(content)
assert len(rows) == 2000
keys = {row.import_key for row in rows}
assert len(keys) == 2000
assert all(row.status == 'resolved' and row.solution for row in rows)
read = lambda name: [json.loads(line) for line in (ROOT / name).read_text(encoding='utf-8').splitlines()]
questions = read('测试问题100题.jsonl')
answers = read('测试参考答案.jsonl')
labels = read('工单原因标注.jsonl')
assert len(questions) == len(answers) == 100
assert len({q['id'] for q in questions}) == 100
assert [q['id'] for q in questions] == [a['id'] for a in answers]
assert {r['import_key'] for r in labels} == keys
assert len({r['scenario_id'] for r in labels}) == 50
for answer in answers:
    assert set(answer['relevant_import_keys']) <= keys
    if answer['type'] == 'diagnose':
        assert len(answer['relevant_import_keys']) == 40
assert len(list((ROOT / 'knowledge').glob('*.md'))) == 4
print(f'验证通过：2000条经项目真实CSV解析器校验，{len(content)}字节；100题答案关联和50场景标注完整。')
