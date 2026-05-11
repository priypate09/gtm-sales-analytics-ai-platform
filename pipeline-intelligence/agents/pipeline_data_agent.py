"""Load sample SFDC opportunities for downstream pipeline agents."""

import yaml
import pandas as pd
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_company_config(root: Path) -> dict:
    cfg_path = root / "company_config.yaml"
    return yaml.safe_load(cfg_path.read_text(encoding="utf-8"))


def validate_opportunities_columns(df: pd.DataFrame) -> str | None:
    # Fail fast if export schema drifts from what downstream agents expect.
    missing = [c for c in ["deal_id", "stage", "close_date", "arr", "rep_name", "account_name"] if c not in df.columns]
    if missing:
        return f"missing columns: {', '.join(missing)}"
    if df["deal_id"].isna().any() or (df["deal_id"].astype(str).str.strip() == "").any():
        return "empty deal_id in one or more rows"
    return None


def opportunities_to_records(df: pd.DataFrame) -> tuple[list[dict], list[str]]:
    records = []
    deal_ids = []
    seen = set()
    # iterrows fine for sample size — swap to df.to_dict('records') if scaling
    for _, row in df.iterrows():
        rec = {
            "deal_id": str(row["deal_id"]).strip(),
            "stage": str(row["stage"]).strip(),
            "close_date": str(row["close_date"]).strip(),
            "arr": int(row["arr"]),
            "rep_name": str(row["rep_name"]).strip(),
            "account_name": str(row["account_name"]).strip(),
        }
        records.append(rec)
        did = rec["deal_id"]
        if did not in seen:
            seen.add(did)
            deal_ids.append(did)
    return records, deal_ids


def run_pipeline_data_agent(root: Path | None = None) -> dict:
    base = root if root is not None else _repo_root()
    agent = "pipeline_data_agent"
    empty = {
        "success": False,
        "agent": agent,
        "message": "",
        "source_path": "",
        "row_count": 0,
        "deal_ids": [],
        "opportunities": [],
    }

    try:
        config = load_company_config(base)
        rel = config["paths"]["sample"]["sfdc_opportunities"]
        csv_path = (base / rel).resolve()
    except (KeyError, TypeError, OSError) as e:
        empty["message"] = f"config or path error: {e}"
        print(f"[PipelineDataAgent] {empty['message']}")
        return empty

    if not csv_path.is_file():
        empty["message"] = f"file not found: {csv_path}"
        empty["source_path"] = str(csv_path)
        print(f"[PipelineDataAgent] {empty['message']}")
        return empty

    print(f"[PipelineDataAgent] loading {csv_path}")
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except (OSError, UnicodeDecodeError, pd.errors.ParserError, ValueError) as e:
        empty["message"] = f"read failed: {e}"
        empty["source_path"] = str(csv_path)
        print(f"[PipelineDataAgent] {empty['message']}")
        return empty

    if df.empty:
        empty["message"] = "CSV has no data rows"
        empty["source_path"] = str(csv_path)
        print(f"[PipelineDataAgent] {empty['message']}")
        return empty

    reason = validate_opportunities_columns(df)
    if reason is not None:
        empty["message"] = reason
        empty["source_path"] = str(csv_path)
        print(f"[PipelineDataAgent] validation failed: {reason}")
        return empty

    opportunities, deal_ids = opportunities_to_records(df)
    n = len(opportunities)
    msg = f"loaded {n} rows ({len(deal_ids)} unique deal_id) from {rel}"
    print(f"[PipelineDataAgent] {msg}")
    return {
        "success": True,
        "agent": agent,
        "message": msg,
        "source_path": str(csv_path),
        "row_count": n,
        "deal_ids": deal_ids,
        "opportunities": opportunities,
    }
