from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

AGENT = "sales_director_agent"
ROOT = Path(__file__).resolve().parents[1]


def _load_config(config_path: Path | None = None) -> dict:
    """Load company config and sales director prompt from disk."""
    path = config_path or ROOT / "company_config.yaml"
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    with (ROOT / "prompts" / "sales_director.yaml").open(encoding="utf-8") as handle:
        config["prompt"] = yaml.safe_load(handle)["sales_director_prompt"]
    return config


def _validate_inputs(crm: dict, market: dict, competitive: dict) -> None:
    """Refuse synthesis unless all three envelopes succeeded with non-empty data."""
    for name, result in (("crm_sync", crm), ("market_intel", market), ("competitive_intel", competitive)):
        if not result.get("success") or not isinstance(result.get("data"), dict) or not result["data"]:
            raise ValueError(f"{name} incomplete: success={result.get('success')} data_empty={not result.get('data')}")


def _build_context(crm: dict, market: dict, competitive: dict, config: dict) -> dict:
    """Build a compact LLM context with flagged_segments as a top-level priority key."""
    crm_d, mkt_d, comp_d = crm["data"], market["data"], competitive["data"]
    pipeline = crm_d.get("pipeline_summary", {}).get("by_segment", {})
    keys = ("name", "lost_arr", "loss_count", "threat_level", "headline", "g2_sentiment", "pricing_signal")
    segments = {
        seg: {
            "current_arr": v.get("current_arr"), "qoq_growth_pct": v.get("qoq_growth_pct"),
            "yoy_growth_pct": v.get("yoy_growth_pct"), "pipeline": pipeline.get(seg, {}),
            "benchmark_growth_pct": mkt_d.get("segments", {}).get(seg, {}).get("benchmark_growth_pct"),
            "gap_pp": mkt_d.get("segments", {}).get(seg, {}).get("gap_pp"),
            "flagged": mkt_d.get("segments", {}).get(seg, {}).get("flagged"),
        }
        for seg, v in crm_d.get("segments", {}).items()
    }
    return {
        "reference_quarter": crm_d.get("reference_quarter"),
        "flagged_segments": mkt_d.get("flagged_segments", []),
        "segments": segments,
        "competitors": [{k: c.get(k) for k in keys} for c in comp_d.get("competitors", [])],
        "gtm_actions_count": int(config["sales_director"]["gtm_actions_count"]),
        "narrative_max_minutes": int(config["sales_director"]["narrative_max_minutes"]),
        "gap_threshold_pp": float(config["gap_threshold_pp"]),
    }


def _parse_json(text: str) -> dict:
    """Parse model JSON with fence strip then regex fallback for long narrative prose."""
    cleaned = text.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            cleaned = fence.group(1).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in synthesis response")
    return json.loads(match.group())


def _synthesize(context: dict, prompt: str, model: str, client: OpenAI) -> dict:
    """Ask GPT-4o to rank GTM actions and write the QBR narrative."""
    n = context["gtm_actions_count"]
    user = f"{prompt}\n\nN={n}\nnarrative_max_minutes={context['narrative_max_minutes']}\n\nContext JSON:\n{json.dumps(context)}"
    text = getattr(client.responses.create(model=model, input=user), "output_text", "") or ""
    if not text:
        raise RuntimeError("Empty synthesis response from model")
    payload = _parse_json(text)
    actions, narrative = payload.get("actions"), payload.get("narrative")
    if not isinstance(actions, list) or len(actions) != n:
        raise ValueError(f"Expected {n} actions, got {0 if not isinstance(actions, list) else len(actions)}")
    if not isinstance(narrative, str) or not narrative.strip():
        raise ValueError("narrative missing or empty")
    return {"actions": actions, "narrative": narrative}


def run(crm_result: dict, market_result: dict, competitive_result: dict, config_path: Path | None = None) -> dict:
    """Validate sub-agent outputs, synthesize top GTM actions, and return QBR narrative."""
    load_dotenv(ROOT / ".env")
    try:
        config = _load_config(config_path)
        model = config.get("openai", {}).get("model")
        if not model or not os.getenv("OPENAI_API_KEY"):
            raise ValueError("openai.model / OPENAI_API_KEY required")
        _validate_inputs(crm_result, market_result, competitive_result)
        print("[Sales Director Agent] All sub-agents confirmed; building synthesis context")
        context = _build_context(crm_result, market_result, competitive_result, config)
        synthesized = _synthesize(context, config["prompt"], model, OpenAI(api_key=os.getenv("OPENAI_API_KEY")))
        data = {
            **synthesized,
            "meta": {
                "model": model, "gtm_actions_count": context["gtm_actions_count"],
                "narrative_max_minutes": context["narrative_max_minutes"],
                "flagged_segments": context["flagged_segments"],
                "inputs_used": ["crm_sync_agent", "market_intel_agent", "competitive_intel_agent"],
            },
        }
        print(f"[Sales Director Agent] Ranked {len(data['actions'])} GTM actions; narrative ready")
        return {"success": True, "agent": AGENT, "message": "Sales director synthesis complete", "data": data}
    except Exception as exc:
        print(f"[Sales Director Agent] Failed: {exc}")
        return {"success": False, "agent": AGENT, "message": str(exc), "data": {}}
