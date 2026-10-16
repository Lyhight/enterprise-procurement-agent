from __future__ import annotations

import argparse
import time

from ..api.dependencies import integration_worker


def main() -> None:
    parser = argparse.ArgumentParser(description="OA/ERP integration job worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    while True:
        job = integration_worker.run_once()
        if job is not None:
            print(f"{job.job_id} {job.target} {job.status}")
        if args.once:
            return
        if job is None:
            time.sleep(max(args.poll_seconds, 0.2))
