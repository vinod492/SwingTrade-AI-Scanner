"""Test fixtures: isolated SQLite database per session, Redis disabled (the
cache layer degrades gracefully), sample data provider."""
import os
import tempfile

_TMPDIR = tempfile.mkdtemp(prefix="swingtrade-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMPDIR}/test.db"
os.environ["REDIS_URL"] = "redis://localhost:1/0"  # unreachable on purpose
os.environ["DATA_PROVIDER"] = "sample"
os.environ["AI_PROVIDER"] = "sample"
os.environ["SECRET_KEY"] = "test-secret"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db.base import reset_engine  # noqa: E402
from app.db.seed import bootstrap  # noqa: E402
from app.main import app  # noqa: E402

reset_engine()


@pytest.fixture(scope="session", autouse=True)
def _quiet_redis_logs():
    import logging

    logging.getLogger("app.services.cache").setLevel(logging.ERROR)


@pytest.fixture()
async def client():
    await bootstrap()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


@pytest.fixture()
async def auth_client(client):
    """Client with a registered user's bearer token attached."""
    import uuid

    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    resp = await client.post("/auth/register", json={"email": email,
                                                     "password": "hunter2hunter2"})
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    client.email = email
    yield client
