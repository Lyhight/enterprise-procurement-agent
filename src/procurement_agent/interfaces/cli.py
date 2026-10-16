from __future__ import annotations

import argparse
import sys

from ..core.config import get_settings
from ..infrastructure.knowledge import KnowledgeBase
from ..infrastructure.repositories import CsvRepository
from ..application.workflow import ProcurementWorkflow


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="分析采购申请")
    parser.add_argument("request_id", nargs="?", default="PR001")
    args = parser.parse_args()

    settings = get_settings()
    repository = CsvRepository(settings.company_data_dir)
    knowledge_base = KnowledgeBase(settings.documents_dir)
    result = ProcurementWorkflow(repository, knowledge_base).analyze(args.request_id)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

