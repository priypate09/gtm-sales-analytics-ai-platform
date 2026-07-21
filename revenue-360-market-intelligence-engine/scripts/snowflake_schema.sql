-- Revenue 360 pipeline output — one row per successful Sales Director run.
-- Apply manually after creating DATABASE / SCHEMA / WAREHOUSE.
-- Table names in company_config.yaml should match (default: REVENUE360.PUBLIC.REVENUE360_RUNS).

CREATE TABLE IF NOT EXISTS REVENUE360.PUBLIC.REVENUE360_RUNS (
    run_id              VARCHAR(36)      NOT NULL,
    written_at          TIMESTAMP_TZ     NOT NULL,
    reference_quarter   VARCHAR(16),
    search_year         NUMBER(4, 0),
    narrative           VARCHAR(16777216),
    actions_json        VARIANT,
    flagged_segments    VARCHAR(512),
    gap_rows            VARIANT,
    CONSTRAINT pk_revenue360_runs PRIMARY KEY (run_id)
);

-- gap_rows VARIANT shape (array of objects):
-- [
--   {
--     "segment": "Enterprise",
--     "internal_yoy_growth_pct": 12.5,
--     "benchmark_growth_pct": 8.0,
--     "gap_pp": 4.5,
--     "flagged": false,
--     "source_summary": "...",
--     "confidence": "medium"
--   }
-- ]
