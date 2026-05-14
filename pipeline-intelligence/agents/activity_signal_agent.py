"""Engagement score and activity-gap signal from SFDC activity log sample CSV."""

import yaml
import pandas as pd
from datetime import date
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_company_config(root: Path) -> dict:
    path = root / "company_config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate_activity_columns(df: pd.DataFrame) -> str | None:
    # Require export shape matching synthetic generator and sample data.
    missing = [c for c in ["deal_id", "activity_type", "activity_date", "contact_role"] if c not in df.columns]
    if missing:
        return f"missing columns: {', '.join(missing)}"
    return None


def engagement_from_signals(
    days_since_last: int,
    activity_count: int,
    max_count: int,
    gap_days: int,
    w_rec: float,
    w_vol: float,
) -> float:
    # Recency tapers to 0 at 2× activity_gap_days; volume is share of max count in this batch.
    denom = 2 * max(int(gap_days), 1)
    recency = max(0.0, 1.0 - float(days_since_last) / float(denom))
    volume = (float(activity_count) / float(max_count)) if max_count > 0 else 0.0
    score = float(w_rec) * recency + float(w_vol) * volume
    return min(1.0, max(0.0, score))

def run_activity_signal_agent(deal_ids: list[str], root: Path | None = None) -> dict:
    # Score each deal from paths.sample.sfdc_activity_log; missing deals get zero engagement and gap flagged.
    agent = "activity_signal_agent"
    if not deal_ids:
        msg = "deal_ids must be a non-empty list"
        print(f"[ActivitySignalAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}

    base = root if root is not None else _repo_root()
    try:
        config = load_company_config(base)
        rel = config["paths"]["sample"]["sfdc_activity_log"]
        gap_days = int(config["scoring"]["activity_gap_days"])
        w_rec = float(config["scoring"]["activity_engagement_weights"]["recency"])
        w_vol = float(config["scoring"]["activity_engagement_weights"]["volume"])
        csv_path = (base / rel).resolve()
    except (KeyError, TypeError, ValueError, OSError) as e:
        msg = f"config or path error: {e}"
        print(f"[ActivitySignalAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}

    if not csv_path.is_file():
        msg = f"file not found: {csv_path}"
        print(f"[ActivitySignalAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}

    print(f"[ActivitySignalAgent] loading {csv_path}")
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except (OSError, UnicodeDecodeError, pd.errors.ParserError, ValueError) as e:
        msg = f"read failed: {e}"
        print(f"[ActivitySignalAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}

    if df.empty:
        msg = "CSV has no data rows"
        print(f"[ActivitySignalAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}
    reason = validate_activity_columns(df)
    if reason is not None:
        print(f"[ActivitySignalAgent] validation failed: {reason}")
        return {"success": False, "agent": agent, "message": reason, "deals": []}

    df = df.copy()
    df["deal_id"] = df["deal_id"].astype(str).str.strip()
    df["_dt"] = pd.to_datetime(df["activity_date"], errors="coerce")
    if df["_dt"].isna().any():
        msg = "invalid or missing activity_date in one or more rows"
        print(f"[ActivitySignalAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}

    today = date.today()
    requested = [str(r).strip() for r in deal_ids if str(r).strip()]
    if not requested:
        msg = "no valid deal_ids after stripping"
        print(f"[ActivitySignalAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}

    counts = df.groupby("deal_id", sort=False).size()
    max_count = 0
    for did in requested:
        if did in counts.index:
            c = int(counts[did])
            if c > max_count:
                max_count = c

    deals_out = []
    for did in requested:
        sub = df[df["deal_id"] == did]
        if sub.empty:
            deals_out.append(
                {
                    "deal_id": did,
                    "engagement_score": 0.0,
                    "activity_gap_flag": True,
                    "last_activity_date": None,
                    "days_since_last": None,
                    "activity_count": 0,
                }
            )
            print(f"[ActivitySignalAgent] no rows for deal_id={did}")
            continue

        last_d = sub["_dt"].max().date()
        n = len(sub)
        days_since = (today - last_d).days
        gap_flag = days_since > gap_days
        score = engagement_from_signals(days_since, n, max_count, gap_days, w_rec, w_vol)
        deals_out.append(
            {
                "deal_id": did,
                "engagement_score": score,
                "activity_gap_flag": gap_flag,
                "last_activity_date": last_d.isoformat(),
                "days_since_last": days_since,
                "activity_count": n,
            }
        )

    msg = f"scored {len(deals_out)} deal(s) from {rel}"
    print(f"[ActivitySignalAgent] {msg}")
    return {
        "success": True,
        "agent": agent,
        "message": msg,
        "deals": deals_out,
    }
