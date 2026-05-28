from __future__ import annotations

from pathlib import Path

import pandas as pd


def ensure_paths(root: Path) -> None:
    expected = [
        "agents",
        "orchestrator",
        "tools",
        "data/synthetic",
        "data/sample",
        "prompts",
        "outputs",
        "tests",
        "company_config.yaml",
        ".env.example",
        ".gitignore",
        "main.py",
        "requirements.txt",
        "README.md",
        "scripts/generate_synthetic_data.py",
        "data/synthetic/sfdc_opportunities.csv",
        "data/synthetic/bookings_revenue.csv",
        "data/sample/sfdc_opportunities.csv",
        "data/sample/bookings_revenue.csv",
    ]
    missing = [path for path in expected if not (root / path).exists()]
    if missing:
        raise RuntimeError(f"Missing expected paths: {missing}")


def ensure_schema_and_ids(root: Path) -> None:
    opp = pd.read_csv(root / "data/synthetic/sfdc_opportunities.csv")
    book = pd.read_csv(root / "data/synthetic/bookings_revenue.csv")
    expected_opp_cols = {
        "opportunity_id",
        "account_name",
        "segment",
        "arr",
        "stage",
        "win_loss_reason",
    }
    expected_book_cols = {
        "opportunity_id",
        "segment",
        "quarter",
        "booked_arr",
        "benchmark_growth_pct",
        "actual_growth_pct",
    }
    if set(opp.columns) != expected_opp_cols:
        raise RuntimeError("Opportunity schema mismatch")
    if set(book.columns) != expected_book_cols:
        raise RuntimeError("Bookings schema mismatch")

    if set(opp["opportunity_id"]) != set(book["opportunity_id"]):
        raise RuntimeError("Opportunity IDs not consistent across CSVs")

    if set(opp["segment"]) != {"Enterprise", "Mid-Market", "SMB"}:
        raise RuntimeError("Segment labels are not exactly expected values")

    arr_min = opp.groupby("segment")["arr"].min().to_dict()
    if arr_min["Enterprise"] < 200_000:
        raise RuntimeError("Enterprise ARR has values below 200k")
    if arr_min["Mid-Market"] < 50_000 or opp[opp["segment"] == "Mid-Market"]["arr"].max() > 200_000:
        raise RuntimeError("Mid-Market ARR range is out of bounds")
    if opp[opp["segment"] == "SMB"]["arr"].max() >= 50_000:
        raise RuntimeError("SMB ARR has values >= 50k")

    if opp["win_loss_reason"].isna().any():
        raise RuntimeError("Win/loss reason has null values")

    quarters = set(book["quarter"].unique())
    if quarters != {"2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"}:
        raise RuntimeError(f"Unexpected quarter coverage: {quarters}")


def ensure_performance_variation(root: Path) -> None:
    book = pd.read_csv(root / "data/synthetic/bookings_revenue.csv")
    by_segment = book.groupby("segment")[["benchmark_growth_pct", "actual_growth_pct"]].mean()
    gaps = by_segment["actual_growth_pct"] - by_segment["benchmark_growth_pct"]
    if not (gaps.min() < 0 and gaps.max() > 0):
        raise RuntimeError("Missing intentional under/over performance variation")


def ensure_gitignore_sanity(root: Path) -> None:
    content = (root / ".gitignore").read_text(encoding="utf-8")
    required_entries = ["data/synthetic/*", "!data/sample/"]
    for entry in required_entries:
        if entry not in content:
            raise RuntimeError(f"Missing .gitignore rule: {entry}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ensure_paths(root)
    ensure_schema_and_ids(root)
    ensure_performance_variation(root)
    ensure_gitignore_sanity(root)
    print("[Revenue360Setup] Verification passed")


if __name__ == "__main__":
    main()
