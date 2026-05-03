"""Load source sales data from CSV into DuckDB."""

from pathlib import Path

import duckdb
import yaml


def load_config(config_path: str) -> dict:
    """Read acquisition settings from YAML config."""
    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    required = {
        "csv_path",
        "duckdb_path",
        "raw_table_name",
        "kaggle_dataset",
        "kaggle_filename",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"Missing config keys: {', '.join(missing)}")
    return config


def fetch_if_missing(config: dict) -> None:
    """Download dataset from Kaggle if not already present locally."""
    source_path = Path(config["csv_path"]).expanduser()
    if source_path.exists():
        print("[DataAcquisitionAgent] Data file found locally, skipping download")
        return

    print("[DataAcquisitionAgent] File not found — downloading from Kaggle...")
    from kaggle.api.kaggle_api_extended import KaggleApi

    source_path.parent.mkdir(parents=True, exist_ok=True)
    api = KaggleApi()
    try:
        api.authenticate()
    except Exception as exc:
        raise RuntimeError(
            "Kaggle authentication failed. Set KAGGLE_API_TOKEN in .env (new KGAT_ token), "
            "or legacy KAGGLE_USERNAME + KAGGLE_KEY, or put the CSV at csv_path locally."
        ) from exc
    api.dataset_download_files(
        config["kaggle_dataset"],
        path=str(source_path.parent),
        unzip=True,
    )

    if not source_path.exists():
        raise FileNotFoundError(
            f"After download, CSV not at {source_path}. "
            f"Set csv_path to match the extracted file ({config['kaggle_filename']}) "
            f"under that folder."
        )

    print(f"[DataAcquisitionAgent] Downloaded → {source_path}")


def ingest_csv_to_duckdb(config: dict) -> dict:
    """Load CSV into DuckDB and return load details."""
    source_path = Path(config["csv_path"]).expanduser()
    if not source_path.exists():
        raise FileNotFoundError(f"CSV file not found: {source_path}")

    db_path = str(Path(config["duckdb_path"]).expanduser())
    table_name = config["raw_table_name"]

    print(f"[DataAcquisitionAgent] Loading {source_path} into {table_name}")
    with duckdb.connect(db_path) as conn:
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE {table_name} AS
            SELECT * FROM read_csv_auto(?, header=true);
            """,
            [str(source_path)],
        )
        rows_loaded = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

    if rows_loaded <= 0:
        raise ValueError("Loaded table has no rows")

    return {
        "success": True,
        "agent": "DataAcquisitionAgent",
        "table_name": table_name,
        "rows_loaded": rows_loaded,
        "db_path": db_path,
        "source_path": str(source_path),
        "message": f"Loaded {rows_loaded} rows into {table_name}",
    }


def run_data_acquisition(config_path: str = "company_config.yaml") -> dict:
    """Run the acquisition workflow and report status."""
    try:
        config = load_config(config_path)
        fetch_if_missing(config)
        result = ingest_csv_to_duckdb(config)
        print(f"[DataAcquisitionAgent] {result['message']}")
        return result
    except Exception as exc:
        message = f"Data acquisition failed: {exc}"
        print(f"[DataAcquisitionAgent] {message}")
        return {"success": False, "agent": "DataAcquisitionAgent", "message": message}
