from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

from tools.openai_web_search import search

AGENT = "market_intel_agent"
ROOT = Path(__file__).resolve().parents[1]


def _load_config(config_path: Path | None = None) -> dict:
    """Load company config and market intel prompt template from disk."""
    path = config_path or ROOT / "company_config.yaml"
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    with (ROOT / "prompts" / "market_intel.yaml").open(encoding="utf-8") as handle:
        config["prompt"] = yaml.safe_load(handle)["market_intel_prompt"]
    return config


def _resolve_segments(crm_data: dict | None, config: dict) -> tuple[list[str], str]:
    """Prefer CRM Sync segment keys so queries stay tied to live pipeline data."""
    if crm_data and crm_data.get("segments"):
        return list(crm_data["segments"].keys()), "crm_sync"
    return list(config["segments"]), "config"


def _build_query(segment: str, config: dict) -> str:
    """Build a live search query from segment + config — never hardcode segments."""
    sources = ", ".join(config["benchmark_sources"])
    year = config["search_year"]
    return (
        f"{config['prompt']}\n\n"
        f"Segment: {segment}\nYear: {year}\nPreferred sources: {sources}\n"
        f"Query focus: {segment} SaaS ARR growth rate benchmark {year}"
    )


def _parse_benchmark(text: str) -> dict:
    """Extract benchmark JSON from model output; fail if growth rate is missing."""
    cleaned = text.strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in search response")
        payload = json.loads(match.group())
    if "benchmark_growth_pct" not in payload:
        raise ValueError("benchmark_growth_pct missing from parsed response")
    return {
        "benchmark_growth_pct": float(payload["benchmark_growth_pct"]),
        "source_summary": str(payload.get("source_summary", "")),
        "confidence": str(payload.get("confidence", "low")),
    }


def run(crm_data: dict | None = None, config_path: Path | None = None) -> dict:
    """Search live benchmarks per segment, parse results, and compute gap vs CRM YoY."""
    load_dotenv(ROOT / ".env")
    try:
        config = _load_config(config_path)
        model = config.get("openai", {}).get("model")
        if not model:
            raise ValueError("openai.model missing from company_config.yaml")
        threshold = float(config["gap_threshold_pp"])
        segments, segments_source = _resolve_segments(crm_data, config)
        print(f"[Market Intel Agent] Searching benchmarks for {len(segments)} segments")

        segment_out: dict = {}
        flagged: list[str] = []
        for segment in segments:
            query = _build_query(segment, config)
            result = search(query, model)
            if not result["success"]:
                raise RuntimeError(f"{segment}: {result['message']}")
            parsed = _parse_benchmark(result["text"])
            entry = {
                "benchmark_growth_pct": parsed["benchmark_growth_pct"],
                "source_summary": parsed["source_summary"],
                "confidence": parsed["confidence"],
                "query": f"{segment} SaaS ARR growth rate benchmark {config['search_year']}",
            }
            crm_seg = (crm_data or {}).get("segments", {}).get(segment)
            if crm_seg and "yoy_growth_pct" in crm_seg:
                internal = float(crm_seg["yoy_growth_pct"])
                gap_pp = round(internal - parsed["benchmark_growth_pct"], 2)
                is_flagged = abs(gap_pp) >= threshold
                entry["internal_yoy_growth_pct"] = internal
                entry["gap_pp"] = gap_pp
                entry["flagged"] = is_flagged
                if is_flagged:
                    flagged.append(segment)
            segment_out[segment] = entry

        data = {
            "search_year": config["search_year"],
            "segments": segment_out,
            "flagged_segments": flagged,
            "meta": {
                "model": model,
                "sources": config["benchmark_sources"],
                "segments_source": segments_source,
                "gap_threshold_pp": threshold,
            },
        }
        print(f"[Market Intel Agent] Benchmarks ready; flagged={flagged}")
        return {"success": True, "agent": AGENT, "message": "Market intel complete", "data": data}
    except Exception as exc:
        print(f"[Market Intel Agent] Failed: {exc}")
        return {"success": False, "agent": AGENT, "message": str(exc), "data": {}}
