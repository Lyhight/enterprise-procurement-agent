from __future__ import annotations

import argparse
import time

from ..api.dependencies import rfq_delivery_worker


def main() -> None:
    parser = argparse.ArgumentParser(description="Supplier RFQ delivery worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    while True:
        delivery = rfq_delivery_worker.run_once()
        if delivery:
            print(f"{delivery.delivery_id} {delivery.rfq_id} {delivery.status}")
        if args.once:
            return
        if delivery is None:
            time.sleep(max(args.poll_seconds, 0.2))
