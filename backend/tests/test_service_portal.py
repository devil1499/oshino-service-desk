import pytest
from httpx import ASGITransport, AsyncClient
from test_postgres_foundation import database as database

from app.main import create_app
from app.seed_service import seed

pytestmark = pytest.mark.postgres


async def test_customer_to_human_and_transfer_preserves_ownership(database, tmp_path, monkeypatch):
    import json

    credentials = tmp_path / "accounts.json"
    await seed(database, credentials)
    people = json.loads(credentials.read_text())
    app = create_app(database)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        headers = {}
        for person in people:
            login = await client.post(
                "/api/auth/login", json={"username": person["username"], "password": person["password"]}
            )
            assert login.status_code == 200, login.text
            headers[person["username"]] = {"Authorization": "Bearer " + login.json()["access_token"]}
        customer = headers["demo_platinum"]
        other = headers["demo_bronze"]
        first, second = headers["demo_l1_lin"], headers["demo_l1_li"]
        products = (await client.get("/api/service/products", headers=customer)).json()
        created = await client.post(
            "/api/service/conversations",
            headers=customer,
            json={"product_id": products[0]["id"], "title": "耳机无法连接"},
        )
        assert created.status_code == 201, created.text
        path = "/api/service/conversations/" + str(created.json()["id"])
        with monkeypatch.context() as patch:
            def no_model():
                raise AssertionError('客户不能通过附加参数调用联网模型')
            patch.setattr('app.modules.service_portal.get_chat_client', no_model)
            from uuid import uuid4
            refused_web = await client.post(path + '/ai', headers=customer, json={
                'request_id': str(uuid4()), 'text': '联网咨询', 'web_search': True,
            })
            assert refused_web.status_code == 422, refused_web.text
        assert (await client.get(path, headers=other)).status_code == 404
        assert (await client.get(path, headers=first)).status_code == 404
        for endpoint in ["/api/users", "/api/tickets", "/api/knowledge", "/api/qa/conversations"]:
            assert (await client.get(endpoint, headers=customer)).status_code == 403
        handoff = {"description": "已经重新配对仍无法连接", "priority": "P2"}
        transferred = await client.post(path + "/handoff", headers=customer, json=handoff)
        assert transferred.status_code == 200, transferred.text
        ticket_id = transferred.json()["ticket_id"]
        repeated = await client.post(path + "/handoff", headers=customer, json=handoff)
        assert repeated.json()["ticket_id"] == ticket_id
        assert (await client.post(path + "/claim", headers=customer)).status_code == 403
        assert (await client.post(path + "/claim", headers=first)).status_code == 200
        assert (await client.post(path + "/claim", headers=second)).status_code == 409
        assert (await client.post(path + "/reply", headers=second, json={"text": "抢答"})).status_code == 403
        assert (await client.post(path + "/reply", headers=first, json={"text": "我会继续协助您"})).status_code == 200
        assert (
            await client.post(path + "/transfer", headers=customer, json={"text": "希望换一位客服", "level": 1})
        ).status_code == 200
        assert (await client.post(path + "/claim", headers=first)).status_code == 409
        assert (await client.post(path + "/claim", headers=second)).status_code == 200
        assert (
            await client.post(path + "/resolve", headers=second, json={"text": "重新配对后恢复连接"})
        ).status_code == 200
        assert (await client.post(path + "/confirm", headers=other)).status_code == 404
        assert (await client.post(path + "/confirm", headers=customer)).json()["status"] == "closed"
        final = (await client.get(path, headers=customer)).json()
        assert final["ticket_id"] == ticket_id
        assert any("希望换一位客服" in record["content"] for record in final["records"])
        assert any("我会继续协助您" in record["content"] for record in final["records"])
        assert (await client.post(path + "/reply", headers=customer, json={"text": "关闭后消息"})).status_code == 409

        # 同严重程度先服务高等级客户；严重程度始终先于客户等级。
        queue = []
        for username, severity in [("demo_champion", "P2"), ("demo_bronze", "P1"), ("demo_platinum", "P2")]:
            person = headers[username]
            conversation = await client.post(
                "/api/service/conversations",
                headers=person,
                json={"product_id": products[0]["id"], "title": "排序验收"},
            )
            address = "/api/service/conversations/" + str(conversation.json()["id"])
            await client.post(
                address + "/handoff", headers=person, json={"description": "功能异常", "priority": severity}
            )
            queue.append((conversation.json()["id"], address))
        listed = (await client.get("/api/service/conversations", headers=first)).json()["items"]
        ids = [row["id"] for row in listed if row["id"] in {item[0] for item in queue}]
        assert ids == [queue[1][0], queue[0][0], queue[2][0]]

        # 并发接单只能成功一次，并且升级后的工单不能被低级客服领取。
        import asyncio

        address = queue[0][1]
        responses = await asyncio.gather(
            client.post(address + "/claim", headers=first), client.post(address + "/claim", headers=second)
        )
        assert sorted(response.status_code for response in responses) == [200, 409]
        winner = first if responses[0].status_code == 200 else second
        assert (
            await client.post(address + "/transfer", headers=winner, json={"text": "需要技术排查", "level": 2})
        ).status_code == 200
        assert (await client.post(address + "/claim", headers=first)).status_code == 403
        assert (await client.post(address + "/claim", headers=headers["demo_l2_zhou"])).status_code == 200
