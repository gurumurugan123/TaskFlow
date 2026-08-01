import json
import uuid

from .models import Job
from redis_client import redis_client


def enqueue_job(payload: dict) -> str:
    """Save job in DB + Redis and push to pending queue. Returns job_id."""
    job_id = str(uuid.uuid4())

    Job.objects.create(
        id=job_id,
        status=Job.STATUS_PENDING,
        payload=payload,
        attempts=0,
    )

    redis_client.hset(
        f"job:{job_id}",
        mapping={
            "id": job_id,
            "status": Job.STATUS_PENDING,
            "payload": json.dumps(payload),
            "attempts": "0",
            "result": "",
        },
    )
    redis_client.lpush("queue:pending", job_id)
    return job_id
