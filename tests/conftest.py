import pytest
import pytest_asyncio
from httpx import AsyncClient

from circuit.main import app


class FakeRedis:
    def __init__(self):
        self.store = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    def expire(self, key, ttl):
        pass


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()

    monkeypatch.setattr(
        "circuit.storage.redis_client.get_redis_client",
        lambda: fake,
    )

    return fake


@pytest.fixture
def fake_postgres(monkeypatch):
    class FakeConn:
        async def execute(self, *args, **kwargs):
            return

    class FakePool:
        async def acquire(self):
            return FakeConn()

        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(
        "circuit.storage.postgres_client.get_pool",
        lambda: FakePool(),
    )


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac