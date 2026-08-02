import json
import time
import uuid

from .constants import (
    BASE_BACKOFF_SECONDS,
    DEAD_LETTER_QUEUE,
    DELAYED_QUEUE,
    MAX_BACKOFF_SECONDS,
    PENDING_QUEUE,
)
from .idempotency import lookup_idempotent_job, save_idempotency_record
from .models import Job
from redis_client import redis_client


def backoff_seconds(attempts: int) -> int:
    """Exponential backoff: 2s, 4s, 8s, ... capped at MAX_BACKOFF_SECONDS."""
    delay = BASE_BACKOFF_SECONDS * (2 ** max(attempts - 1, 0))
    return min(delay, MAX_BACKOFF_SECONDS)


def _create_and_enqueue(job_id: str, payload: dict) -> str:
    """Create job in DB + Redis and push to pending queue."""
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
    redis_client.lpush(PENDING_QUEUE, job_id)
    return job_id


def enqueue_job(payload: dict, idempotency_key: str | None = None) -> tuple[str, bool]:
    """
    Enqueue a background job.

    Returns:
        (job_id, created)
    """
    if idempotency_key:
        existing_job_id, is_replay = lookup_idempotent_job(idempotency_key, payload)
        if is_replay:
            return existing_job_id, False

    job_id = str(uuid.uuid4())
    _create_and_enqueue(job_id, payload)

    if idempotency_key:
        save_idempotency_record(idempotency_key, job_id, payload)

    return job_id, True


def schedule_retry(job_id: str, attempts: int, error: str) -> int:
    """Move failed job to delayed queue with exponential backoff. Returns delay seconds."""
    delay = backoff_seconds(attempts)
    run_at = time.time() + delay
    redis_client.zadd(DELAYED_QUEUE, {job_id: run_at})
    retry_info = {
        "retry_scheduled": True,
        "error": error,
        "attempts": attempts,
        "retry_in_seconds": delay,
        "retry_at": run_at,
    }
    redis_client.hset(
        f"job:{job_id}",
        mapping={
            "status": Job.STATUS_PENDING,
            "attempts": str(attempts),
            "result": json.dumps(retry_info),
        },
    )
    try:
        job = Job.objects.get(id=job_id)
        job.status = Job.STATUS_PENDING
        job.attempts = attempts
        job.result = retry_info
        job.save(update_fields=["status", "attempts", "result"])
    except Job.DoesNotExist:
        pass
    return delay


def move_to_dead_letter(job_id: str, attempts: int, error: str) -> None:
    """Permanently failed job → dead-letter queue."""
    dead_info = {"error": error, "attempts": attempts, "dead_letter": True}
    redis_client.lpush(DEAD_LETTER_QUEUE, job_id)
    redis_client.hset(
        f"job:{job_id}",
        mapping={
            "status": Job.STATUS_FAILED,
            "attempts": str(attempts),
            "result": json.dumps(dead_info),
        },
    )
    try:
        job = Job.objects.get(id=job_id)
        job.status = Job.STATUS_FAILED
        job.attempts = attempts
        job.result = dead_info
        job.save(update_fields=["status", "attempts", "result"])
    except Job.DoesNotExist:
        pass


def promote_delayed_jobs() -> int:
    """Move jobs whose backoff time has passed from delayed → pending queue."""
    now = time.time()
    ready_jobs = redis_client.zrangebyscore(DELAYED_QUEUE, 0, now)
    promoted = 0
    for job_id in ready_jobs:
        if redis_client.zrem(DELAYED_QUEUE, job_id):
            redis_client.lpush(PENDING_QUEUE, job_id)
            promoted += 1
    return promoted


def list_dead_letter_jobs(limit: int = 50) -> list[str]:
    """Return job ids currently in the dead-letter queue."""
    return redis_client.lrange(DEAD_LETTER_QUEUE, 0, max(limit - 1, 0))
