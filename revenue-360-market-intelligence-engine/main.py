from pathlib import Path

from agents.crm_sync_agent import run as run_crm_sync


def main() -> None:
    print("[Main] Revenue 360 setup scaffold is ready.")
    print(f"[Main] Project root: {Path(__file__).resolve().parent}")
    print(f"[Main] CRM Sync smoke test: {run_crm_sync()}")


if __name__ == "__main__":
    main()
