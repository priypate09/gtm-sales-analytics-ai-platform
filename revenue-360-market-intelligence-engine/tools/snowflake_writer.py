from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

TOOL = "snowflake_writer"
ROOT = Path(__file__).resolve().parents[1]


def _load_config(config_path: Path | None = None) -> dict:
    """Load company config for persistence flag and table names."""
    path = config_path or ROOT / "company_config.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _fqn(config: dict) -> str:
    """Build fully-qualified table name from config snowflake block."""
    sf = config.get("snowflake", {})
    return f'{sf["database"]}.{sf["schema"]}.{sf["table_runs"]}'


def _build_row(consolidated: dict) -> dict:
    """Flatten gap rows + narrative into one REVENUE360_RUNS payload."""
    market = consolidated.get("market_intel", {}).get("data", {})
    sales = consolidated.get("sales_director", {}).get("data", {})
    crm = consolidated.get("crm_sync", {}).get("data", {})
    segments = market.get("segments", {})
    gap_rows = [
        {
            "segment": seg,
            "internal_yoy_growth_pct": entry.get("internal_yoy_growth_pct"),
            "benchmark_growth_pct": entry.get("benchmark_growth_pct"),
            "gap_pp": entry.get("gap_pp"),
            "flagged": bool(entry.get("flagged")),
            "source_summary": entry.get("source_summary", ""),
            "confidence": entry.get("confidence", ""),
        }
        for seg, entry in segments.items()
    ]
    flagged = market.get("flagged_segments") or sales.get("meta", {}).get("flagged_segments") or []
    return {
        "run_id": str(uuid.uuid4()),
        "written_at": datetime.now(timezone.utc).isoformat(),
        "reference_quarter": crm.get("reference_quarter"),
        "search_year": market.get("search_year"),
        "narrative": sales.get("narrative", ""),
        "actions_json": json.dumps(sales.get("actions", [])),
        "flagged_segments": ",".join(flagged),
        "gap_rows": gap_rows,
    }


def _log_dry_run(table: str, row: dict) -> None:
    """Print what would be written without opening a Snowflake connection."""
    print(
        f"[SnowflakeWriter] Dry-run: would write 1 row to {table} "
        f"(run_id={row['run_id']}, gap_segments={len(row['gap_rows'])}, "
        f"flagged={row['flagged_segments'] or 'none'})"
    )


def _connect():
    """Open a Snowflake connection from env — password auth only."""
    import snowflake.connector  # lazy: only needed when persist_to_snowflake is true

    required = (
        "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD",
        "SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA",
    )
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise ValueError(f"Missing Snowflake env vars: {', '.join(missing)}")
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
        role=os.getenv("SNOWFLAKE_ROLE") or None,
    )


def _insert_row(conn, table: str, row: dict) -> None:
    """Insert one pipeline-run row into REVENUE360_RUNS."""
    sql = f"""
        INSERT INTO {table} (
            run_id, written_at, reference_quarter, search_year,
            narrative, actions_json, flagged_segments, gap_rows
        ) SELECT %s, %s::TIMESTAMP_TZ, %s, %s, %s, PARSE_JSON(%s), %s, PARSE_JSON(%s)
    """
    params = (
        row["run_id"], row["written_at"], row["reference_quarter"], row["search_year"],
        row["narrative"], row["actions_json"], row["flagged_segments"],
        json.dumps(row["gap_rows"]),
    )
    with conn.cursor() as cur:
        cur.execute(sql, params)


def write(consolidated: dict, config: dict | None = None, config_path: Path | None = None) -> dict:
    """Persist one pipeline run to Snowflake, or dry-run when the config flag is false."""
    load_dotenv(ROOT / ".env")
    try:
        cfg = config if config is not None else _load_config(config_path)
        table = _fqn(cfg)
        row = _build_row(consolidated)
        if not cfg.get("persist_to_snowflake", False):
            _log_dry_run(table, row)
            return {
                "success": True, "tool": TOOL,
                "message": "Dry-run: Snowflake write skipped",
                "data": {"dry_run": True, "table": table, "run_id": row["run_id"]},
            }
        print(f"[SnowflakeWriter] Writing run {row['run_id']} to {table}")
        conn = _connect()
        try:
            _insert_row(conn, table, row)
        finally:
            conn.close()
        print(f"[SnowflakeWriter] Write complete: {row['run_id']}")
        return {
            "success": True, "tool": TOOL,
            "message": "Snowflake write complete",
            "data": {"dry_run": False, "table": table, "run_id": row["run_id"]},
        }
    except Exception as exc:
        print(f"[SnowflakeWriter] Failed: {exc}")
        return {"success": False, "tool": TOOL, "message": str(exc), "data": {}}
