from __future__ import annotations

from pathlib import Path
import random

from faker import Faker
import pandas as pd
import yaml


SEED = 360
SEGMENTS = ("Enterprise", "Mid-Market", "SMB")
QUARTERS = ("2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4")
BENCHMARK_GROWTH = {"Enterprise": 12.0, "Mid-Market": 10.0, "SMB": 8.0}
ACTUAL_GROWTH = {"Enterprise": 15.0, "Mid-Market": 5.0, "SMB": 9.0}
WIN_REASONS = ("Won on product fit", "Won with executive alignment")
NON_COMPETITIVE_LOSS = ("Lost due to missing feature", "Lost due to implementation risk")
LOSS_THEMES = ("pricing", "product fit")


def _load_competitor_pool(root: Path) -> list[str]:
    """Read data-gen competitor names from config — never used by the agent."""
    with (root / "company_config.yaml").open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    pool = config.get("data_generation", {}).get("competitor_pool") or []
    if not pool:
        raise ValueError("data_generation.competitor_pool missing from company_config.yaml")
    return list(pool)


def _arr_for_segment(segment: str, rng: random.Random) -> int:
    if segment == "Enterprise":
        return rng.randint(200_000, 750_000)
    if segment == "Mid-Market":
        return rng.randint(50_000, 199_999)
    return rng.randint(8_000, 49_999)


def _win_loss_reason(stage: str, competitors: list[str], rng: random.Random) -> str:
    """Closed-lost competitive rows embed a named competitor for agent extraction."""
    if stage == "Closed Won":
        return rng.choice(WIN_REASONS)
    if rng.random() < 0.65:
        name = rng.choice(competitors)
        theme = rng.choice(LOSS_THEMES)
        return f"Lost to {name} on {theme}"
    return rng.choice(NON_COMPETITIVE_LOSS)


def build_opportunities(
    fake: Faker, rng: random.Random, competitors: list[str], count_per_segment: int = 12
) -> pd.DataFrame:
    rows: list[dict] = []
    for segment in SEGMENTS:
        for _ in range(count_per_segment):
            stage = rng.choice(("Closed Won", "Closed Lost"))
            rows.append(
                {
                    "opportunity_id": f"OPP-{fake.unique.random_number(digits=7, fix_len=True)}",
                    "segment": segment,
                    "account_name": fake.company(),
                    "arr": _arr_for_segment(segment, rng),
                    "stage": stage,
                    "win_loss_reason": _win_loss_reason(stage, competitors, rng),
                }
            )
    return pd.DataFrame(rows)


def build_bookings(opportunities: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
    base_by_segment = {"Enterprise": 4_000_000, "Mid-Market": 2_000_000, "SMB": 900_000}
    rows: list[dict] = []
    for segment, df in opportunities.groupby("segment"):
        start_value = base_by_segment[segment]
        growth = ACTUAL_GROWTH[segment] / 100.0
        quarter_values = [
            start_value,
            start_value * (1 + growth / 3),
            start_value * (1 + (2 * growth) / 3),
            start_value * (1 + growth),
        ]
        for quarter, quarter_total in zip(QUARTERS, quarter_values):
            weights = [rng.random() for _ in range(len(df))]
            weight_sum = sum(weights)
            for (_, row), weight in zip(df.iterrows(), weights):
                rows.append(
                    {
                        "opportunity_id": row["opportunity_id"],
                        "segment": segment,
                        "quarter": quarter,
                        "booked_arr": round((quarter_total * weight) / weight_sum, 2),
                        "benchmark_growth_pct": BENCHMARK_GROWTH[segment],
                        "actual_growth_pct": ACTUAL_GROWTH[segment],
                    }
                )
    return pd.DataFrame(rows)


def select_sample_opportunity_ids(opportunities: pd.DataFrame, per_segment: int = 5) -> set[str]:
    # Build one deterministic ID source used by both sample outputs.
    sample_rows = opportunities.groupby("segment", group_keys=False).head(per_segment)
    return set(sample_rows["opportunity_id"].tolist())


def write_outputs(opportunities: pd.DataFrame, bookings: pd.DataFrame, root: Path) -> None:
    synthetic_dir = root / "data" / "synthetic"
    sample_dir = root / "data" / "sample"
    synthetic_dir.mkdir(parents=True, exist_ok=True)
    sample_dir.mkdir(parents=True, exist_ok=True)

    opportunities.to_csv(synthetic_dir / "sfdc_opportunities.csv", index=False)
    bookings.to_csv(synthetic_dir / "bookings_revenue.csv", index=False)

    sample_opp_ids = select_sample_opportunity_ids(opportunities, per_segment=5)
    sample_opportunities = opportunities[opportunities["opportunity_id"].isin(sample_opp_ids)]
    sample_bookings = bookings[bookings["opportunity_id"].isin(sample_opp_ids)]

    sample_opportunities.to_csv(sample_dir / "sfdc_opportunities.csv", index=False)
    sample_bookings.to_csv(sample_dir / "bookings_revenue.csv", index=False)


def main() -> None:
    fake = Faker()
    fake.seed_instance(SEED)
    rng = random.Random(SEED)
    root = Path(__file__).resolve().parents[1]
    competitors = _load_competitor_pool(root)
    opportunities = build_opportunities(fake, rng, competitors)
    bookings = build_bookings(opportunities, rng)
    write_outputs(opportunities, bookings, root)
    print(f"[DataGen] Generated synthetic datasets with seed {SEED}.")


if __name__ == "__main__":
    main()
