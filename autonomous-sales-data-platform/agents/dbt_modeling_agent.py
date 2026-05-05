"""Run dbt models against the project DuckDB database."""

import json
import os
from pathlib import Path

import yaml
from dbt.cli.main import dbtRunner, dbtRunnerResult

_REQ = frozenset({"duckdb_path", "dbt_project_dir", "dbt_profiles_dir", "dbt_target"})


def _print_run_results_summary(project_dir: str) -> None:
    """Print one line per node from target/run_results.json."""
    path = Path(project_dir) / "target" / "run_results.json"
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    rows = payload.get("results", [])
    for row in rows:
        uid = row.get("unique_id", "")
        name = uid.split(".")[-1] if uid else "?"
        status = row.get("status", "?")
        secs = round(float(row.get("execution_time") or 0), 2)
        print(f"[DbtModelingAgent] {name} -> {status} ({secs}s)")
    n, fails = len(rows), sum(1 for r in rows if r.get("status") == "error")
    print(f"[DbtModelingAgent] Total models run: {n}, failures: {fails}")


def run_dbt_modeling(config_path: str = "company_config.yaml") -> dict:
    """Load config, run dbt programmatically, return result dict."""
    try:
        root = Path(config_path).resolve().parent
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        if missing := sorted(_REQ - cfg.keys()):
            raise ValueError(f"Missing config keys: {', '.join(missing)}")

        project_dir = str((root / cfg["dbt_project_dir"]).resolve())
        profiles_dir = str((root / cfg["dbt_profiles_dir"]).resolve())
        duck = Path(cfg["duckdb_path"]).expanduser()
        os.environ["DUCKDB_PATH"] = str((duck if duck.is_absolute() else root / duck).resolve())

        print(f"[DbtModelingAgent] running dbt — {project_dir}")
        result: dbtRunnerResult = dbtRunner().invoke(
            [
                "run",
                "--project-dir",
                project_dir,
                "--profiles-dir",
                profiles_dir,
                "--target",
                str(cfg["dbt_target"]),
            ]
        )

        if not result.success:
            raise RuntimeError("dbt run reported failure — check model output above")

        _print_run_results_summary(project_dir)

        msg = "dbt run completed successfully"
        print(f"[DbtModelingAgent] {msg}")
        return {"success": True, "agent": "DbtModelingAgent", "message": msg}

    except Exception as exc:
        msg = f"dbt modeling failed: {exc}"
        print(f"[DbtModelingAgent] {msg}")
        return {"success": False, "agent": "DbtModelingAgent", "message": msg}