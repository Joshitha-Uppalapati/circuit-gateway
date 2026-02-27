import os
import redis
from dotenv import load_dotenv

load_dotenv()


def get_redis_client() -> redis.Redis | None:
    url = os.getenv("REDIS_URL")
    if not url:
        return None

    try:
        # test connection before returning
        client = redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        return client
    except redis.ConnectionError:
        return None