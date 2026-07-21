# CRM-first then Market+Competitive fan-out (not fully concurrent): Market Intel needs CRM Sync segments for benchmark queries.
from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from agents.competitive_intel_agent import run as run_competitive_intel
from agents.crm_sync_agent import run as run_crm_sync
from agents.market_intel_agent import run as run_market_intel
from agents.sales_director_agent import run as run_sales_director
from tools.snowflake_writer import write as write_snowflake

AGENT = "revenue_360_orchestrator"
ROOT = Path(__file__).resolve().parents[1]


def _load_config(config_path: Path | None = None) -> dict:
    """Load orchestrator settings from company config."""
    path = config_path or ROOT / "company_config.yaml"
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _is_complete(result: dict) -> bool:
    """True when an agent envelope succeeded with a non-empty data dict."""
    return bool(result.get("success") and isinstance(result.get("data"), dict) and result["data"])


async def _run_with_retry(label: str, fn, retry_attempts: int, *args, **kwargs) -> dict:
    """Run a sync agent in a thread; retry that agent only on failure."""
    total = retry_attempts + 1
    last: dict = {"success": False, "agent": label, "message": "not started", "data": {}}
    for attempt in range(1, total + 1):
        if attempt > 1:
            print(f"[Revenue 360] Retrying {label} attempt {attempt}/{total}")
        try:
            last = await asyncio.to_thread(fn, *args, **kwargs)
        except Exception as exc:
            print(f"[Revenue 360] {label} raised on attempt {attempt}/{total}: {exc}")
            last = {"success": False, "agent": label, "message": str(exc), "data": {}}
            continue
        if _is_complete(last):
            return last
        print(f"[Revenue 360] {label} failed attempt {attempt}/{total}: {last.get('message')}")
    return last


def _all_complete(crm: dict, market: dict, competitive: dict) -> bool:
    """Gate handoff until CRM, Market, and Competitive all confirm."""
    return _is_complete(crm) and _is_complete(market) and _is_complete(competitive)


def _assemble(crm: dict, market: dict, competitive: dict, sales: dict, config: dict) -> dict:
    """Build the consolidated pipeline payload for callers."""
    orch = config.get("orchestrator", {})
    return {
        "crm_sync": crm,
        "market_intel": market,
        "competitive_intel": competitive,
        "sales_director": sales,
        "meta": {
            "retry_attempts": int(orch.get("retry_attempts", 0)),
            "handoff_trigger": orch.get("handoff_trigger", "all_sub_agents_completed"),
        },
    }


async def _run_async(config_path: Path | None = None) -> dict:
    """CRM Sync first, then concurrent Market+Competitive, then Sales Director."""
    config = _load_config(config_path)
    retries = int(config.get("orchestrator", {}).get("retry_attempts", 0))
    print("[Revenue 360] Starting pipeline: CRM Sync first")
    crm = await _run_with_retry("crm_sync_agent", run_crm_sync, retries, config_path)
    if not _is_complete(crm):
        return {"success": False, "agent": AGENT, "message": f"CRM Sync failed: {crm.get('message')}", "data": {}}

    print("[Revenue 360] Fan-out: Market Intel + Competitive Intel")
    market, competitive = await asyncio.gather(
        _run_with_retry("market_intel_agent", run_market_intel, retries, crm["data"], config_path),
        _run_with_retry("competitive_intel_agent", run_competitive_intel, retries, config_path),
    )
    if not _all_complete(crm, market, competitive):
        msg = (
            f"Sub-agents incomplete — market={market.get('success')} "
            f"competitive={competitive.get('success')}"
        )
        print(f"[Revenue 360] {msg}")
        return {"success": False, "agent": AGENT, "message": msg, "data": _assemble(crm, market, competitive, {}, config)}

    print("[Revenue 360] all_sub_agents_completed — invoking Sales Director")
    sales = await asyncio.to_thread(run_sales_director, crm, market, competitive, config_path)
    if not _is_complete(sales):
        return {
            "success": False, "agent": AGENT,
            "message": f"Sales Director failed: {sales.get('message')}",
            "data": _assemble(crm, market, competitive, sales, config),
        }
    assembled = _assemble(crm, market, competitive, sales, config)
    # Best-effort: dry-run or write failure must not fail an already-successful run.
    try:
        snowflake = write_snowflake(assembled, config)
    except Exception as exc:
        print(f"[Revenue 360] Snowflake persistence raised: {exc}")
        snowflake = {"success": False, "tool": "snowflake_writer", "message": str(exc), "data": {}}
    assembled["meta"]["snowflake"] = {
        "success": snowflake.get("success"),
        "message": snowflake.get("message"),
        **(snowflake.get("data") or {}),
    }
    print("[Revenue 360] Pipeline complete")
    return {
        "success": True, "agent": AGENT, "message": "Revenue 360 pipeline complete",
        "data": assembled,
    }


def run(config_path: Path | None = None) -> dict:
    """Sync entry point that drives the async Revenue 360 pipeline."""
    return asyncio.run(_run_async(config_path))
