from pathlib import Path

from agents.crm_sync_agent import run as run_crm_sync
from agents.market_intel_agent import run as run_market_intel


def main() -> None:
    print("[Main] Revenue 360 setup scaffold is ready.")
    print(f"[Main] Project root: {Path(__file__).resolve().parent}")
    crm = run_crm_sync()
    print(f"[Main] CRM Sync smoke test: {crm}")
    market = run_market_intel(crm_data=crm.get("data") if crm.get("success") else None)
    print(f"[Main] Market Intel smoke test: {market}")


if __name__ == "__main__":
    main()
