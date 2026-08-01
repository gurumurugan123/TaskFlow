"""
Background worker: pull jobs from Redis and process them.
Run separately from Django: python worker.py
"""

import json
import os
import time
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "taskflow.settings")
django.setup()

from django.conf import settings

from jobs.models import Job
from jobs.pdf_utils import write_simple_pdf
from redis_client import redis_client

PENDING_QUEUE = "queue:pending"
PROCESSING_QUEUE = "queue:processing"
PDF_OUTPUT_DIR = Path(settings.BASE_DIR) / "media" / "pdfs"


def prepare_pdf(job_id: str, data: dict) -> dict:
    """Background work: build a PDF file on disk."""
    title = data.get("title") or "Untitled"
    content = data.get("content") or ""

    # Simulate slower PDF work (report generation, etc.)
    time.sleep(2)

    output_path = PDF_OUTPUT_DIR / f"{job_id}.pdf"
    write_simple_pdf(output_path, title=title, content=content)

    return {
        "ok": True,
        "task": "prepare_pdf",
        "file_path": str(output_path),
        "title": title,
    }


def process_job(job_id: str, payload: dict) -> dict:
    """Run the actual work for a job. Extend this with real task handlers."""
    task = payload.get("task")
    data = payload.get("data", {})

    if task == "prepare_pdf":
        return prepare_pdf(job_id, data)

    if task == "send_email":
        # Placeholder: replace with real email send later
        time.sleep(2)
        return {"ok": True, "task": task, "to": data.get("to")}

    if task == "demo":
        time.sleep(1)
        return {"ok": True, "task": task, "message": "demo completed"}

    raise ValueError(f"Unknown task: {task}")


def update_job(job_id: str, status: str, result=None, attempts=None):
    """Update Redis hash and Postgres Job row."""
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
        print(f"[worker] warning: job {job_id} not found in DB")


def run_worker():
    print("[worker] started — waiting for jobs on queue:pending")
    while True:
        # Atomically move job from pending → processing
        job_id = redis_client.brpoplpush(PENDING_QUEUE, PROCESSING_QUEUE, timeout=0)
        if not job_id:
            continue

        print(f"[worker] picked job {job_id}")
        job_data = redis_client.hgetall(f"job:{job_id}")
        if not job_data:
            print(f"[worker] missing Redis hash for {job_id}, skipping")
            redis_client.lrem(PROCESSING_QUEUE, 1, job_id)
            continue

        payload_raw = job_data.get("payload", "{}")
        try:
            payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
        except json.JSONDecodeError:
            payload = {}

        attempts = int(job_data.get("attempts") or 0) + 1
        update_job(job_id, Job.STATUS_PROCESSING, attempts=attempts)

        try:
            result = process_job(job_id, payload)
            update_job(job_id, Job.STATUS_COMPLETED, result=result, attempts=attempts)
            print(f"[worker] completed job {job_id}")
        except Exception as exc:
            update_job(
                job_id,
                Job.STATUS_FAILED,
                result={"error": str(exc)},
                attempts=attempts,
            )
            print(f"[worker] failed job {job_id}: {exc}")
        finally:
            redis_client.lrem(PROCESSING_QUEUE, 1, job_id)


if __name__ == "__main__":
    run_worker()
