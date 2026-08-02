"""
Simple load test: POST many jobs and report timings.

Usage:
    python load_test.py --count 50
    python load_test.py --count 100 --workers 10 --task demo

Requires: Django runserver running on BASE_URL
"""

import argparse
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE_URL = "http://127.0.0.1:8000"


def create_job(session: requests.Session, task: str, index: int) -> dict:
    payload = {
        "task": task,
        "data": {"index": index},
    }
    if task == "fail_demo":
        payload["data"]["fail_until_attempt"] = 3

    started = time.perf_counter()
    response = session.post(
        f"{BASE_URL}/jobs/",
        json=payload,
        headers={"Idempotency-Key": str(uuid.uuid4())},
        timeout=30,
    )
    elapsed = time.perf_counter() - started
    return {
        "status_code": response.status_code,
        "elapsed": elapsed,
        "body": response.json() if response.content else {},
    }


def main():
    parser = argparse.ArgumentParser(description="TaskFlow load test")
    parser.add_argument("--count", type=int, default=50, help="Number of jobs to create")
    parser.add_argument("--workers", type=int, default=5, help="Parallel HTTP threads")
    parser.add_argument("--task", default="demo", help="Task name (demo, fail_demo, etc.)")
    args = parser.parse_args()

    print(f"Load test: {args.count} jobs, task={args.task}, parallel={args.workers}")
    session = requests.Session()
    results = []
    started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(create_job, session, args.task, i)
            for i in range(args.count)
        ]
        for future in as_completed(futures):
            results.append(future.result())

    total = time.perf_counter() - started
    ok = sum(1 for r in results if r["status_code"] in (200, 201, 202))
    avg = sum(r["elapsed"] for r in results) / len(results) if results else 0

    print(f"Done in {total:.2f}s")
    print(f"Success: {ok}/{args.count}")
    print(f"Avg API latency: {avg:.3f}s")
    print("Run multiple workers: python run_workers.py --count 3")


if __name__ == "__main__":
    main()
