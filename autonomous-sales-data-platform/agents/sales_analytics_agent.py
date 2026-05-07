"""Generate GTM markdown analytics from DuckDB marts via OpenAI Chat Completions."""

import json
import os
from pathlib import Path

import duckdb
import yaml
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

_REQ = frozenset({"duckdb_path", "analytics_report_path", "openai_model"})


def collect_mart_metrics(config: dict, project_root: Path) -> dict:
    """Query fct_revenue and fct_segment_performance; return KPI facts."""
    duck = Path(config["duckdb_path"]).expanduser()
    db = str((duck if duck.is_absolute() else project_root / duck).resolve())
    q_seg = "SELECT * FROM main.fct_segment_performance ORDER BY 1"
    q_sum = """
                SELECT
                    sum(total_sales)   AS total_sales,
                    sum(total_profit)  AS total_profit,
                    sum(order_count)   AS total_orders,
                    avg(avg_deal_size) AS avg_deal_size
                FROM main.fct_revenue
            """
    q_prod = """SELECT product, sum(total_sales) AS sales, sum(total_profit) AS profit
                FROM main.fct_revenue GROUP BY 1 ORDER BY sales DESC LIMIT 5"""
    q_reg = """SELECT region, sum(total_sales) AS sales, sum(total_profit) AS profit
                FROM main.fct_revenue GROUP BY 1 ORDER BY sales DESC LIMIT 5"""
    q_trend = """
                SELECT date_trunc('month', order_date) AS month,
                    sum(total_sales)  AS sales,
                    sum(total_profit) AS profit,
                    sum(order_count)  AS orders
                FROM main.fct_revenue
                GROUP BY 1 ORDER BY 1
                """
    q_cross_seg_prod = """
                        SELECT segment,
                            region,
                            subregion,
                            sum(total_sales)  AS sales,
                            sum(order_count)  AS orders
                        FROM main.fct_revenue
                        GROUP BY 1, 2, 3 ORDER BY sales DESC LIMIT 10
                        """
    print(f"[SalesAnalyticsAgent] reading marts from {db}")
    with duckdb.connect(db) as conn:
        seg = conn.execute(q_seg).fetchdf().to_dict(orient="records")
        revenue_totals = conn.execute(q_sum).fetchdf().to_dict(orient="records")[0]
        prods = conn.execute(q_prod).fetchdf().to_dict(orient="records")
        regs = conn.execute(q_reg).fetchdf().to_dict(orient="records")
        trend = conn.execute(q_trend).fetchdf().to_dict(orient="records")
        cross_seg_prod = conn.execute(q_cross_seg_prod).fetchdf().to_dict(orient="records")
    return {
        "revenue_totals":      revenue_totals,
        "segment_performance": seg,
        "top_products":        prods,
        "top_regions":         regs,
        "monthly_trend":       trend,
        "segment_by_region":   cross_seg_prod,
    }


def generate_report_markdown(metrics: dict, model: str) -> str:
    """Call OpenAI Chat Completions to turn KPI facts into a GTM markdown report."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set — add it to your environment or .env")
    client = OpenAI()
    system = (
        "You are a GTM analytics writer. Given JSON KPI facts from B2B SaaS sales marts, "
        "write markdown: title, executive summary, KPI bullets using ONLY provided numbers, "
        "segment comparison, product and region highlights, 3-5 actionable recommendations, "
        "and a short data limits note. Do not invent metrics."
    )
    user = "KPI JSON:\n" + json.dumps(metrics, indent=2, default=str)
    print(f"[SalesAnalyticsAgent] OpenAI Chat Completions — model={model}")
    rsp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
    )
    text = (rsp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("OpenAI returned empty content")
    return text


def run_sales_analytics(config_path: str = "company_config.yaml") -> dict:
    """Load config, pull marts, generate markdown via LLM, write report file."""
    try:
        root = Path(config_path).resolve().parent
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        if missing := sorted(_REQ - cfg.keys()):
            raise ValueError(f"Missing config keys: {', '.join(missing)}")
        metrics = collect_mart_metrics(cfg, root)
        md = generate_report_markdown(metrics, str(cfg["openai_model"]))
        out = Path(cfg["analytics_report_path"]).expanduser()
        out_path = out if out.is_absolute() else (root / out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        msg = f"wrote report -> {out_path.resolve()}"
        print(f"[SalesAnalyticsAgent] {msg}")
        return {
            "success": True,
            "agent": "SalesAnalyticsAgent",
            "message": msg,
            "report_path": str(out_path.resolve()),
        }
    except Exception as exc:
        msg = f"sales analytics failed: {exc}"
        print(f"[SalesAnalyticsAgent] {msg}")
        return {
            "success": False,
            "agent": "SalesAnalyticsAgent",
            "message": msg,
            "report_path": None,
        }
