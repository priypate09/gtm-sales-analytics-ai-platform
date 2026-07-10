from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv
from openai import OpenAI

from tools.exa_search import search

AGENT = "competitive_intel_agent"
ROOT = Path(__file__).resolve().parents[1]
COMPETITOR_RE = re.compile(r"^Lost to (.+?) on (.+)$")


def _load_config(config_path: Path | None = None) -> dict:
    """Load company config and competitive intel prompt from disk."""
    path = config_path or ROOT / "company_config.yaml"
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    with (ROOT / "prompts" / "competitive_intel.yaml").open(encoding="utf-8") as handle:
        config["prompt"] = yaml.safe_load(handle)["competitive_intel_prompt"]
    config["opportunities_path"] = ROOT / config["data_paths"]["opportunities_csv"]
    return config


def _extract_competitors(opp: pd.DataFrame) -> list[dict]:
    """Parse competitor names from closed-lost win/loss reasons at runtime."""
    stats: dict[str, dict] = {}
    for _, row in opp[opp["stage"] == "Closed Lost"].iterrows():
        match = COMPETITOR_RE.match(str(row["win_loss_reason"]).strip())
        if not match:
            continue
        name, theme = match.group(1).strip(), match.group(2).strip()
        entry = stats.setdefault(name, {"name": name, "loss_count": 0, "lost_arr": 0.0, "loss_themes": set()})
        entry["loss_count"] += 1
        entry["lost_arr"] += float(row["arr"])
        entry["loss_themes"].add(theme)
    ranked = sorted(stats.values(), key=lambda i: (-i["lost_arr"], -i["loss_count"], i["name"]))
    for item in ranked:
        item["lost_arr"] = round(item["lost_arr"], 2)
        item["loss_themes"] = sorted(item["loss_themes"])
    return ranked


def _synthesize(competitor: str, snippets: list[dict], prompt: str, model: str, client: OpenAI) -> dict:
    """Ask GPT-4o to turn Exa snippets into structured competitive signals."""
    blob = "\n\n".join(f"Title: {s['title']}\nURL: {s['url']}\nSnippet: {s['snippet']}" for s in snippets)
    text = getattr(client.responses.create(
        model=model, input=f"{prompt}\n\nCompetitor: {competitor}\n\nSearch snippets:\n{blob}"
    ), "output_text", "") or ""
    if not text:
        raise RuntimeError(f"Empty synthesis response for {competitor}")
    try:
        payload = json.loads(text.strip())
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in signal response")
        payload = json.loads(match.group())
    return {k: ([str(x) for x in payload.get(k, [])] if k == "recent_launches" else str(payload.get(k, d)))
            for k, d in (("g2_sentiment", "mixed"), ("g2_summary", ""), ("pricing_signal", ""),
                         ("recent_launches", []), ("threat_level", "medium"), ("headline", ""))}


def run(config_path: Path | None = None) -> dict:
    """Extract competitors from SFDC losses, search Exa, and return a threat summary."""
    load_dotenv(ROOT / ".env")
    try:
        config = _load_config(config_path)
        model = config.get("openai", {}).get("model")
        if not model or not os.getenv("OPENAI_API_KEY"):
            raise ValueError("openai.model / OPENAI_API_KEY required")
        top_n = int(config["competitive_intel"]["top_n_competitors"])
        max_results = int(config["exa_search"]["max_results"])
        days_back = int(config["exa_search"]["days_back"])
        opp_path = config["opportunities_path"]
        if not opp_path.exists():
            raise FileNotFoundError(f"Opportunities CSV not found: {opp_path}")
        print("[Competitive Intel Agent] Extracting competitors from closed-lost reasons")
        ranked = _extract_competitors(pd.read_csv(opp_path))[:top_n]
        if not ranked:
            raise ValueError("No named competitors found in closed-lost win_loss_reason")
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        competitors_out = []
        for item in ranked:
            name = item["name"]
            query = f"{name} G2 reviews pricing product launch SaaS"
            print(f"[Competitive Intel Agent] Exa search for {name}")
            exa = search(query, max_results, days_back)
            if not exa["success"]:
                raise RuntimeError(f"{name}: {exa['message']}")
            signals = _synthesize(name, exa["results"], config["prompt"], model, client)
            competitors_out.append({
                **item, **signals, "sources": [r["url"] for r in exa["results"] if r.get("url")], "query": query,
            })
        top_threats = [c["name"] for c in competitors_out]
        data = {
            "competitors": competitors_out,
            "threat_summary": {
                "top_threats": top_threats,
                "headline": competitors_out[0].get("headline") or f"Top threat: {top_threats[0]}",
                "recommended_watchlist": top_threats,
            },
            "meta": {
                "model": model, "exa_max_results": max_results, "days_back": days_back,
                "top_n_competitors": top_n, "competitors_source": "sfdc_win_loss_reason",
                "opportunities_path": str(opp_path),
            },
        }
        print(f"[Competitive Intel Agent] Threat summary ready; top={top_threats}")
        return {"success": True, "agent": AGENT, "message": "Competitive intel complete", "data": data}
    except Exception as exc:
        print(f"[Competitive Intel Agent] Failed: {exc}")
        return {"success": False, "agent": AGENT, "message": str(exc), "data": {}}
