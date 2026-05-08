"""Run all four agents in a sequential fail-fast pipeline."""

import sys
from pathlib import Path

from dotenv import load_dotenv

from agents.data_acquisition_agent import run_data_acquisition
from agents.data_quality_agent import run_data_quality
from agents.dbt_modeling_agent import run_dbt_modeling
from agents.sales_analytics_agent import run_sales_analytics


def main() -> None:
    """Run acquisition, dbt, quality, and analytics in order."""
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")
    config_path = sys.argv[1] if len(sys.argv) > 1 else "company_config.yaml"

    print("[Pipeline] Starting DataAcquisitionAgent")
    result = run_data_acquisition(config_path)
    if not result["success"]:
        print(result["message"])
        sys.exit(1)

    print("[Pipeline] Starting DataQualityAgent")
    result = run_data_quality(config_path)
    if not result["success"]:
        print(result["message"])
        sys.exit(1)

    print("[Pipeline] Starting DbtModelingAgent")
    result = run_dbt_modeling(config_path)
    if not result["success"]:
        print(result["message"])
        sys.exit(1)

    print("[Pipeline] Starting SalesAnalyticsAgent")
    result = run_sales_analytics(config_path)
    if not result["success"]:
        print(result["message"])
        sys.exit(1)

    print("[Pipeline] Complete - all 4 agents passed")


if __name__ == "__main__":
    main()
