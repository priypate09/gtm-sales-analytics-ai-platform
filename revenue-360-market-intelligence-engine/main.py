from pathlib import Path

from agents.crm_sync_agent import run as run_crm_sync
from agents.market_intel_agent import run as run_market_intel
from agents.competitive_intel_agent import run as run_competitive_intel
from agents.sales_director_agent import run as run_sales_director


def main() -> None:
    print("[Main] Revenue 360 setup scaffold is ready.")
    print(f"[Main] Project root: {Path(__file__).resolve().parent}")

    crm = run_crm_sync()
    print(f"[Main] CRM Sync smoke test: {crm['success']}")

    market = run_market_intel(crm_data=crm.get("data") if crm.get("success") else None)
    print(f"[Main] Market Intel smoke test: {market['success']}")

    competitive = run_competitive_intel()
    print(f"[Main] Competitive Intel smoke test: {competitive['success']}")

    if crm["success"] and market["success"] and competitive["success"]:
        sales = run_sales_director(
            crm_result=crm,
            market_result=market,
            competitive_result=competitive,
        )
        print(f"[Main] Sales Director smoke test: {sales}")
    else:
        print("[Main] Skipping Sales Director — one or more sub-agents failed")


if __name__ == "__main__":
    main()