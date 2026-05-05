"""Run data quality checks on the raw DuckDB table using pandas."""

from pathlib import Path
import duckdb
import pandas as pd
import yaml

_REQUIRED = {"duckdb_path", "raw_table_name", "dq_min_row_count",
             "dq_sales_column", "dq_segment_column",
             "dq_sales_max_null_rate", "dq_segment_allowed"}


def validate_raw_table(df: pd.DataFrame, config: dict) -> list[dict]:
    """Five checks on a dataframe; returns list of name/passed/detail dicts."""
    sales = config["dq_sales_column"]
    seg   = config["dq_segment_column"]

    checks = [
        {
            "name": "row_count_minimum",
            "passed": len(df) >= config["dq_min_row_count"],
            "detail": f"count={len(df)}, min={config['dq_min_row_count']}"
        },
        {
            "name": "sales_column_exists",
            "passed": sales in df.columns,
            "detail": f"'{sales}' present={sales in df.columns}"
        },
        {
            "name": "sales_null_rate",
            "passed": df[sales].isna().mean() < config["dq_sales_max_null_rate"],
            "detail": f"rate={df[sales].isna().mean():.5f}, max={config['dq_sales_max_null_rate']}"
        },
        {
            "name": "sales_positive_nonnull",
            "passed": (df[sales].dropna() > 0).all(),
            "detail": f"nonpositive_nonnull={(df[sales].dropna() <= 0).sum()}"
        },
        {
            "name": "segment_allowed_nonnull",
            "passed": df[seg].isin(config["dq_segment_allowed"]).all(),
            "detail": f"invalid_or_null={(~df[seg].isin(config['dq_segment_allowed'])).sum()}"
        },
    ]
    return checks


def run_data_quality(config_path: str = "company_config.yaml") -> dict:
    """Load config, read table into pandas, run checks, return result dict."""
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        if missing := sorted(_REQUIRED - cfg.keys()):
            raise ValueError(f"Missing config keys: {', '.join(missing)}")

        db_path = str(Path(cfg["duckdb_path"]).expanduser())
        with duckdb.connect(db_path) as conn:
            df = conn.execute(f"SELECT * FROM {cfg['raw_table_name']}").df()

        cfg["dq_segment_allowed"] = list(cfg["dq_segment_allowed"])
        checks = validate_raw_table(df, cfg)

        for c in checks:
            print(f"[DataQualityAgent] {'ok' if c['passed'] else 'FAIL'} {c['name']}: {c['detail']}")

        ok  = all(c["passed"] for c in checks)
        msg = "All data quality checks passed" if ok else "Data quality checks failed"
        print(f"[DataQualityAgent] {msg}")
        return {"success": ok, "agent": "DataQualityAgent", "message": msg, "checks": checks}

    except Exception as exc:
        msg = f"Data quality failed: {exc}"
        print(f"[DataQualityAgent] {msg}")
        return {"success": False, "agent": "DataQualityAgent", "message": msg, "checks": []}