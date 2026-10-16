from __future__ import annotations

import argparse
import json

from ..application.maintenance import AgentDataMaintenance
from ..core.config import get_settings
from ..infrastructure.memory import AgentMemoryStore
from ..infrastructure.tracing import AgentTraceStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent data retention maintenance")
    parser.add_argument("--trace-days", type=int, default=90)
    parser.add_argument("--memory-days", type=int, default=365)
    parser.add_argument(
        "--delete", action="store_true", help="Apply deletion; default is preview only"
    )
    parser.add_argument("--delete-failed-traces", action="store_true")
    parser.add_argument("--delete-approval-memories", action="store_true")
    args = parser.parse_args()

    database_path = get_settings().database_path
    traces = AgentTraceStore(database_path)
    memories = AgentMemoryStore(database_path)
    traces.initialize()
    memories.initialize()
    report = AgentDataMaintenance(traces, memories).run(
        trace_days=args.trace_days,
        memory_days=args.memory_days,
        preserve_failed_runs=not args.delete_failed_traces,
        preserve_approval_memories=not args.delete_approval_memories,
        dry_run=not args.delete,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
