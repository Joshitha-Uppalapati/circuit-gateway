import os
import redis
from dotenv import load_dotenv

load_dotenv()


def get_redis_client() -> redis.Redis | None:
    url = os.getenv("REDIS_URL")

    if not url:
        print("redis not configured")
        return None

    try:
        client = redis.Redis.from_url(url, decode_responses=True)

        client.ping()

        return client

    except redis.ConnectionError as e:
        print("redis not reachable, falling back:", e)
        return None