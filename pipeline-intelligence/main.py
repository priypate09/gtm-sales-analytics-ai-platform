"""CLI entry point for the pipeline intelligence orchestrator."""

import sys
from pathlib import Path

from dotenv import load_dotenv

from orchestrator.pipeline_intelligence import run_pipeline_intelligence

DEFAULT_QUERY = "Assess deal health and slip risk for loaded opportunities"


def main() -> None:
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")
    query = " ".join(sys.argv[1:]).strip() or DEFAULT_QUERY
    out = run_pipeline_intelligence(query, root)
    print(f"success={out.get('success')} message={out.get('message')}")
    if out.get("report_path"):
        print(f"report: {out['report_path']}")
    if not out.get("topic_allowed", True):
        sys.exit(1)
    if not out.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
tic.