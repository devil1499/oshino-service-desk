"""通过本地项目API导入本批数据，不修改已有记录，不重启服务。"""
import csv
import io
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
rows = list(csv.DictReader((ROOT / '工单2000条.csv').open(encoding='utf-8-sig', newline='')))
def identity(row):
    return (row['title'], row['customer_email'], row['description'], row['solution'])
source_keys = {identity(row): row['import_key'] for row in rows}
labels = [json.loads(line) for line in (ROOT / '工单原因标注.jsonl').read_text(encoding='utf-8').splitlines()]
credentials = json.loads((PROJECT / '.local/docker-admin.json').read_text(encoding='utf-8-sig'))

with httpx.Client(base_url='http://127.0.0.1:8000/api', timeout=180) as client:
    def call(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if not response.is_success:
            raise RuntimeError(f'{method} {path}: HTTP {response.status_code}: {response.text[:500]}')
        return response.json()

    login = call('POST', '/auth/login', json={k: credentials[k] for k in ('username', 'password')})
    client.headers['Authorization'] = 'Bearer ' + login['access_token']
    assert login['user']['role'] == 'admin'

    def catalog(kind):
        result = []
        page = 1
        while True:
            batch = call('GET', f'/config/{kind}', params={'page': page, 'page_size': 100})
            result.extend(batch)
            if len(batch) < 100:
                return result
            page += 1

    products, modules, categories = catalog('products'), catalog('modules'), catalog('categories')
    def ensure(items, kind, name, product_id=None):
        found = next((x for x in items if x['name'] == name and
                      (product_id is None or x['product_id'] == product_id)), None)
        if found:
            if not found['is_active']:
                raise RuntimeError(f'基础资料已停用，未自动更改：{name}')
            return found['id']
        payload = {'name': name}
        if product_id is not None:
            payload['product_id'] = product_id
        found = call('POST', '/config/' + kind, json=payload)
        items.append(found)
        return found['id']

    product_id = ensure(products, 'products', '演示协作平台')
    module_ids = {name: ensure(modules, 'modules', name, product_id) for name in {r['module'] for r in rows}}
    category_ids = {name: ensure(categories, 'categories', name) for name in {r['category'] for r in rows}}
    existing = {}
    page = 1
    while True:
        batch = call('GET', '/tickets', params={'imported_only': True, 'product_id': product_id, 'page': page, 'page_size': 100})
        for row in batch['items']:
            key = source_keys.get(identity(row))
            if key:
                existing[key] = row['id']
        if page * 100 >= batch['total']:
            break
        page += 1
    missing = [r for r in rows if r['import_key'] not in existing]
    if missing:
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(missing)
        result = call('POST', '/tickets/import', files={'file': ('synthetic-2000.csv', output.getvalue().encode('utf-8-sig'), 'text/csv')})
        assert result['imported'] == len(missing)
        existing.update(zip((r['import_key'] for r in missing), result['ticket_ids'], strict=True))
    print(f'工单：新增{len(missing)}条，已有{2000-len(missing)}条。', flush=True)
    documents = []
    by_key = {r['import_key']: r for r in rows}
    seen = set()
    for label in labels:
        scenario = label['scenario_id']
        if scenario in seen:
            continue
        seen.add(scenario)
        row = by_key[label['import_key']]
        title = f'合成演示20261102 {scenario}：' + row['title'].split('（')[0].removeprefix('模拟：')
        matches = call('GET', '/knowledge', params={'q': title})['items']
        doc = next((x for x in matches if x['title'] == title), None)
        if doc is None:
            content = (f'# {title}\n\n产品：演示协作平台。仅用于合成演示，不是真实已办结记录。\n\n'
                       f'## 判断依据\n{label["evidence"]}\n\n## 原因与处理\n{row["solution"]}\n\n'
                       '## 信息不足时\n先追问错误提示、发生时间、影响范围与已尝试步骤，不能只凭现象直接定因。')
            doc = call('POST', '/knowledge', json={'title': title, 'content': content, 'product_id': product_id,
                       'module_id': module_ids[row['module']], 'category_id': category_ids[row['category']]})
        if doc['status'] == 'draft':
            doc = call('POST', f'/knowledge/{doc["id"]}/publish')
        if doc['status'] != 'published':
            raise RuntimeError('本批知识存在停用文档，未自动启用')
        documents.append({'scenario_id': scenario, 'document_id': doc['id'], 'chunk_count': doc['chunk_count']})
    # 回读接口验证，不用写入成功响应代替实际核对。
    keys = set()
    page = 1
    while True:
        batch = call('GET', '/tickets', params={'imported_only': True, 'product_id': product_id, 'page': page, 'page_size': 100})
        keys.update(source_keys.get(identity(r)) for r in batch['items'])
        if page * 100 >= batch['total']:
            break
        page += 1
    assert all(r['import_key'] in keys for r in rows)
    report = {'imported_now': len(missing), 'verified_tickets': 2000, 'documents': documents,
              'ticket_ids': {r['import_key']: existing[r['import_key']] for r in rows},
              'index_rebuilt': False}
    (ROOT / '导入结果.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'回读确认2000条工单；已发布{len(documents)}份场景知识。未重启服务、未重建向量索引。')
