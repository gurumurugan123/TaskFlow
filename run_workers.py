"""
Start multiple TaskFlow workers in parallel.

All workers share queue:pending — Redis BRPOPLPUSH ensures each job
goes to exactly one worker.

Usage:
    python run_workers.py
    python run_workers.py --count 5

Stop all workers with Ctrl+C.
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multiple TaskFlow workers")
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Number of worker processes to start (default: 3)",
    )
    args = parser.parse_args()

    if args.count < 1:
        print("Error: --count must be at least 1")
        sys.exit(1)

    worker_script = ROOT / "worker.py"
    python = sys.executable
    processes: list[subprocess.Popen] = []

    print(f"Starting {args.count} workers from {worker_script}")
    print("Press Ctrl+C to stop all workers\n")

    for i in range(1, args.count + 1):
        env = os.environ.copy()
        env["WORKER_ID"] = f"worker-{i}"
        proc = subprocess.Popen(
            [python, str(worker_script)],
            env=env,
            cwd=str(ROOT),
        )
        processes.append(proc)
        print(f"  worker-{i} started (pid {proc.pid})")

    def shutdown(*_args) -> None:
        print("\nStopping all workers...")
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("All workers stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            for proc in processes:
                if proc.poll() is not None:
                    print(f"Worker pid {proc.pid} exited unexpectedly (code {proc.returncode})")
                    shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
