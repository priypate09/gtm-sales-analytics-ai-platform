from pathlib import Path

import pandas as pd
import yaml

AGENT = "crm_sync_agent"
ROOT = Path(__file__).resolve().parents[1]

def _load_config(config_path: Path | None = None) -> dict:
    """Load yaml config and resolve CRM CSV paths relative to project root."""
    path = config_path or ROOT / "company_config.yaml"
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    config["opportunities_path"] = ROOT / config["data_paths"]["opportunities_csv"]
    config["bookings_path"] = ROOT / config["data_paths"]["bookings_csv"]
    return config

def _load_csv(path: Path, required: set[str]) -> pd.DataFrame:
    """Load a CRM CSV and fail fast when expected columns are missing."""
    df = pd.read_csv(path)
    if missing := required - set(df.columns):
        raise ValueError(f"{path.name} missing columns: {missing}")
    return df

def _aggregate_segment_quarterly_arr(bookings: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Sum booked_arr by segment and quarter for growth math."""
    result: dict[str, dict[str, float]] = {}
    for (segment, quarter), arr in bookings.groupby(["segment", "quarter"])["booked_arr"].sum().items():
        result.setdefault(segment, {})[quarter] = round(float(arr), 2)
    return result

def _compute_growth_rates(quarterly: dict[str, float]) -> tuple[float, float, str, str]:
    """Derive headline QoQ and within-year YoY from ordered quarter totals."""
    quarters = sorted(quarterly.keys())
    if len(quarters) < 2:
        raise ValueError("Need at least 2 quarters for growth calculations")
    first_q, prior_q, latest_q = quarters[0], quarters[-2], quarters[-1]
    q1, prior, latest = quarterly[first_q], quarterly[prior_q], quarterly[latest_q]
    return round(((latest - prior) / prior) * 100, 2), round(((latest - q1) / q1) * 100, 2), latest_q, prior_q

def _build_segment_arr_dict(segments: list[str], aggregated: dict[str, dict[str, float]]) -> dict:
    """Assemble per-segment ARR totals and growth rates for orchestrator handoff."""
    result = {}
    for segment in segments:
        quarterly = aggregated.get(segment)
        if not quarterly:
            raise ValueError(f"No bookings data for configured segment: {segment}")
        qoq, yoy, latest_q, prior_q = _compute_growth_rates(quarterly)
        result[segment] = {
            "current_arr": quarterly[latest_q],
            "prior_quarter_arr": quarterly[prior_q],
            "first_quarter_arr": quarterly[sorted(quarterly)[0]],
            "quarterly_arr": quarterly,
            "qoq_growth_pct": qoq,
            "yoy_growth_pct": yoy,
        }
    return result

def run(config_path: Path | None = None) -> dict:
    """Load CRM CSVs, compute segment ARR growth, and return structured output."""
    try:
        config = _load_config(config_path)
        if config.get("crm_mode") != "csv":
            return {"success": False, "agent": AGENT, "message": "MCP mode not implemented", "data": {}}
        opp_path, book_path = config["opportunities_path"], config["bookings_path"]
        if not opp_path.exists() or not book_path.exists():
            raise FileNotFoundError("One or more CRM CSV files not found")
        print("[CRM Sync Agent] Loading opportunities and bookings CSVs")
        opp = _load_csv(opp_path, {"opportunity_id", "segment", "arr", "stage", "win_loss_reason"})
        book = _load_csv(book_path, {"opportunity_id", "segment", "quarter", "booked_arr"})
        if set(opp["opportunity_id"]) != set(book["opportunity_id"]):
            raise ValueError("Opportunity IDs not consistent across CSVs")
        aggregated = _aggregate_segment_quarterly_arr(book)
        segment_data = _build_segment_arr_dict(config["segments"], aggregated)
        quarters = sorted(aggregated[config["segments"][0]].keys())
        by_segment = {
            segment: {
                "count": len(df),
                "closed_won": int((df["stage"] == "Closed Won").sum()),
                "closed_lost": int((df["stage"] == "Closed Lost").sum()),
                "total_pipeline_arr": round(float(df["arr"].sum()), 2),
            }
            for segment, df in opp.groupby("segment")
        }
        data = {
            "reference_quarter": quarters[-1],
            "prior_quarter": quarters[-2],
            "segments": segment_data,
            "pipeline_summary": {"total_opportunities": len(opp), "by_segment": by_segment},
            "meta": {"crm_mode": config["crm_mode"], "opportunities_path": str(opp_path),
                     "bookings_path": str(book_path), "quarters_available": quarters},
        }
        print(f"[CRM Sync Agent] Computed ARR growth for {len(segment_data)} segments")
        return {"success": True, "agent": AGENT, "message": "CRM sync complete", "data": data}
    except Exception as exc:
        print(f"[CRM Sync Agent] Failed: {exc}")
        return {"success": False, "agent": AGENT, "message": str(exc), "data": {}}
