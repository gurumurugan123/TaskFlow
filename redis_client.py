import os
import redis
from dotenv import load_dotenv

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(redis_url)
