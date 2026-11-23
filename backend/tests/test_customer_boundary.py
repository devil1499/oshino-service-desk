import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import get_current_user
from app.main import create_app
from app.models import User
from tests.test_foundation import make_test_settings


@pytest.mark.parametrize('path', ['/api/tickets', '/api/users', '/api/qa/conversations'])
async def test_customer_cannot_read_staff_endpoints(path):
    app = create_app(make_test_settings(), recover_jobs=False)
    app.dependency_overrides[get_current_user] = lambda: User(
        id=90, username='customer_test', display_name='测试客户', role='customer', is_active=True,
    )
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app), base_url='http://test',
    ) as client:
        response = await client.get(path)
    assert response.status_code == 403
