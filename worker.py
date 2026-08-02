"""
Background worker: pull jobs from Redis and process them.

Run a single worker:
    python worker.py

Run multiple workers (recommended):
    python run_workers.py
    python run_workers.py --count 5

Or manually in separate terminals:
    python worker.py
    set WORKER_ID=worker-2 && python worker.py   (Windows cmd)
    $env:WORKER_ID="worker-2"; python worker.py  (PowerShell)
"""

import json
import os
import time
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "taskflow.settings")
django.setup()

from django.conf import settings

import redis

from jobs.constants import MAX_RETRIES, PENDING_QUEUE, PROCESSING_QUEUE
from jobs.models import Job
from jobs.pdf_utils import write_simple_pdf
from jobs.queue import move_to_dead_letter, promote_delayed_jobs, schedule_retry
from redis_client import redis_client

WORKER_ID = os.getenv("WORKER_ID") or os.getenv("HOSTNAME", "worker-1")
PDF_OUTPUT_DIR = Path(settings.BASE_DIR) / "media" / "pdfs"


def log(message: str) -> None:
    print(f"[{WORKER_ID}] {message}")


def prepare_pdf(job_id: str, data: dict) -> dict:
    title = data.get("title") or "Untitled"
    content = data.get("content") or ""
    time.sleep(2)
    output_path = PDF_OUTPUT_DIR / f"{job_id}.pdf"
    write_simple_pdf(output_path, title=title, content=content)
    return {"ok": True, "task": "prepare_pdf", "file_path": str(output_path), "title": title}


def process_job(job_id: str, payload: dict, attempts: int) -> dict:
    task = payload.get("task")
    data = payload.get("data", {})

    if task == "prepare_pdf":
        return prepare_pdf(job_id, data)

    if task == "send_email":
        time.sleep(2)
        return {"ok": True, "task": task, "to": data.get("to")}

    if task == "demo":
        time.sleep(1)
        return {"ok": True, "task": task, "message": "demo completed"}

    # Test task: fails until attempt N (for retry/backoff testing)
    if task == "fail_demo":
        fail_until = int(data.get("fail_until_attempt", MAX_RETRIES))
        if attempts < fail_until:
            raise RuntimeError(f"Simulated failure on attempt {attempts}/{fail_until}")
        return {"ok": True, "task": task, "attempts": attempts}

    raise ValueError(f"Unknown task: {task}")


def update_job(job_id: str, status: str, result=None, attempts=None):
    mapping = {"status": status}
    if result is not None:
        mapping["result"] = json.dumps(result)
    if attempts is not None:
        mapping["attempts"] = str(attempts)

    redis_client.hset(f"job:{job_id}", mapping=mapping)

    try:
        job = Job.objects.get(id=job_id)
        job.status = status
        fields = ["status"]
        if result is not None:
            job.result = result
            fields.append("result")
        if attempts is not None:
            job.attempts = attempts
            fields.append("attempts")
        job.save(update_fields=fields)
    except Job.DoesNotExist:
        log(f"warning: job {job_id} not found in DB")


def handle_failure(job_id: str, attempts: int, exc: Exception) -> None:
    error = str(exc)
    if attempts < MAX_RETRIES:
        delay = schedule_retry(job_id, attempts, error)
        log(f"job {job_id} failed (attempt {attempts}), retry in {delay}s")
    else:
        move_to_dead_letter(job_id, attempts, error)
        log(f"job {job_id} moved to dead-letter queue after {attempts} attempts")


def process_one_job(job_id: str) -> None:
    job_data = redis_client.hgetall(f"job:{job_id}")
    if not job_data:
        log(f"missing Redis hash for {job_id}, skipping")
        redis_client.lrem(PROCESSING_QUEUE, 1, job_id)
        return

    payload_raw = job_data.get("payload", "{}")
    try:
        payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
    except json.JSONDecodeError:
        payload = {}

    attempts = int(job_data.get("attempts") or 0) + 1
    update_job(job_id, Job.STATUS_PROCESSING, attempts=attempts)

    try:
        result = process_job(job_id, payload, attempts)
        update_job(job_id, Job.STATUS_COMPLETED, result=result, attempts=attempts)
        log(f"completed job {job_id}")
    except Exception as exc:
        handle_failure(job_id, attempts, exc)
    finally:
        redis_client.lrem(PROCESSING_QUEUE, 1, job_id)


def run_worker():
    log("started — waiting on queue:pending (multiple workers OK)")
    while True:
        promoted = promote_delayed_jobs()
        if promoted:
            log(f"promoted {promoted} delayed job(s) to pending")

        try:
            job_id = redis_client.brpoplpush(PENDING_QUEUE, PROCESSING_QUEUE, timeout=5)
        except (redis.exceptions.TimeoutError, redis.exceptions.ConnectionError) as exc:
            log(f"Redis connection issue while waiting: {exc}. Retrying...")
            time.sleep(1)
            continue

        if not job_id:
            continue

        log(f"picked job {job_id}")
        process_one_job(job_id)


if __name__ == "__main__":
    run_worker()
