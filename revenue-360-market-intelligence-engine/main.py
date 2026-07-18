from pathlib import Path

from orchestrator.revenue_360 import run as run_orchestrator


def main() -> None:
    """Run the full Revenue 360 pipeline through the orchestrator."""
    root = Path(__file__).resolve().parent
    print(f"[Main] Starting Revenue 360 pipeline from {root}")
    result = run_orchestrator()
    print(f"[Main] success={result['success']} message={result['message']}")
    if not result["success"]:
        return
    sales = result["data"].get("sales_director", {}).get("data", {})
    actions = sales.get("actions", [])
    narrative = sales.get("narrative", "")
    print(f"[Main] GTM actions ranked: {len(actions)}")
    if narrative:
        preview = narrative[:200] + ("..." if len(narrative) > 200 else "")
        print(f"[Main] Narrative preview: {preview}")


if __name__ == "__main__":
    main()
