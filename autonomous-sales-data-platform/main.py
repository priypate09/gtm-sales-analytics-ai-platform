"""Entry point to run agents locally (e.g. data acquisition)."""

from pathlib import Path

from dotenv import load_dotenv

from agents.data_acquisition_agent import run_data_acquisition


def main() -> None:
    """Run DataAcquisitionAgent using company_config.yaml"""
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")
    config_path = root / "company_config.yaml"
    result = run_data_acquisition(str(config_path))
    if not result.get("success"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
