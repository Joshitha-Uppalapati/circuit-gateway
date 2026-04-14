import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

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

    def hset(self, key, mapping=None, **kwargs):
        if mapping:
            self.store.setdefault(key, {}).update(mapping)

    def hmget(self, key, *fields):
        bucket = self.store.get(key, {})
        return [bucket.get(f) for f in fields]

    def expire(self, key, ttl):
        pass

    def register_script(self, script):
        def run(keys=None, args=None):
            capacity = int(args[0]) if args else 0
            return [1, capacity, 0]  # allow request
        return run


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
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac