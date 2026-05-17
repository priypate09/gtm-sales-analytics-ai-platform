"""Forecast adjustment markdown for deals handed off when slip_risk exceeds threshold."""

import os
from datetime import datetime, timezone
from pathlib import Path

import yaml
from anthropic import Anthropic

SYSTEM_PROMPT = (
    "You are a B2B sales forecast specialist. Respond in markdown only. "
    "Recommend a concrete forecast change using only the provided data. Do not invent CRM fields."
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_company_config(root: Path) -> dict:
    path = root / "company_config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _agent_fail(agent: str, msg: str, n: int = 0) -> dict:
    return {"success": False, "agent": agent, "message": msg, "handoff_count": n,
            "report_path": None, "markdown": "", "deals": []}


def _deal_row(did: str, slip_f: float | None, llm_ok: bool, md: str, msg: str) -> dict:
    return {"deal_id": did, "slip_risk_score": slip_f, "llm_ok": llm_ok,
            "forecast_adjustment_md": md, "message": msg}


def build_forecast_prompt(handoff: dict, trigger: float) -> str:
    # Structured facts keep the model from hallucinating fields not in the handoff bundle.
    opp, sig = handoff.get("opportunity") or {}, handoff.get("signals") or {}
    lines = [
        f"deal_id: {handoff.get('deal_id', '')}",
        f"slip_risk_score: {handoff.get('slip_risk_score', '')} (handoff threshold: {trigger})",
        f"account: {opp.get('account_name', '')} | stage: {opp.get('stage', '')}",
        f"close_date: {opp.get('close_date', '')} | arr: {opp.get('arr', '')} | rep: {opp.get('rep_name', '')}",
        f"engagement_score: {sig.get('engagement_score', '')} | activity_gap_flag: {sig.get('activity_gap_flag', '')}",
        f"sentiment_score: {sig.get('sentiment_score', '')} | tone_trajectory: {sig.get('tone_trajectory', '')}",
        f"sentiment_decline_flag: {sig.get('sentiment_decline_flag', '')}",
        "rag_summary:",
        str(handoff.get("rag_summary") or ""),
        "Write: ### Signals summary, ### Evidence, ### Recommendation, ### Next steps",
    ]
    return "\n".join(lines)


def call_forecast_llm(system: str, user: str, config: dict) -> tuple[str | None, str]:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None, "ANTHROPIC_API_KEY not set"
    try:
        resp = Anthropic(api_key=key).messages.create(
            model=str(config["llm"]["model"]),
            max_tokens=int(config["llm"]["max_tokens"]),
            temperature=float(config["llm"]["temperature"]),
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text = str(getattr(block, "text", "")).strip()
                if text:
                    return text, ""
        return None, "empty LLM response"
    except Exception as e:
        return None, str(e)


def run_forecast_specialist_agent(handoffs: list[dict], root: Path | None = None) -> dict:
    # Partial success: one failed LLM call does not abort the rest of the handoff batch.
    agent = "forecast_specialist_agent"
    if not handoffs:
        print("[ForecastSpecialist] no handoffs")
        return _agent_fail(agent, "no handoffs")
    base = root if root is not None else _repo_root()
    try:
        config = load_company_config(base)
        trigger = float(config["scoring"]["handoff_trigger"])
        report_path = (base / config["paths"]["outputs"]["deal_health_report"]).resolve()
    except (KeyError, TypeError, ValueError, OSError) as e:
        msg = f"config error: {e}"
        print(f"[ForecastSpecialist] {msg}")
        return _agent_fail(agent, msg, len(handoffs))

    deals_out, sections, ok_count = [], [], 0
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for h in handoffs:
        did = str(h.get("deal_id", "")).strip()
        if not did:
            print("[ForecastSpecialist] skipping blank deal_id")
            continue
        try:
            slip_f = float(h.get("slip_risk_score"))
        except (TypeError, ValueError):
            print(f"[ForecastSpecialist] invalid slip_risk_score for {did}")
            deals_out.append(_deal_row(did, None, False, "", "invalid slip_risk_score"))
            continue
        if slip_f <= trigger:
            print(f"[ForecastSpecialist] skip {did}: slip_risk {slip_f} <= {trigger}")
            deals_out.append(
                _deal_row(did, slip_f, False, "", f"slip_risk_score {slip_f} not above handoff_trigger {trigger}")
            )
            continue
        opp = h.get("opportunity") or {}
        header = f"## Forecast adjustment — {did} ({opp.get('account_name') or did})"
        print(f"[ForecastSpecialist] calling LLM for deal_id={did}")
        md, err = call_forecast_llm(SYSTEM_PROMPT, build_forecast_prompt(h, trigger), config)
        if md:
            ok_count += 1
            body = f"{header}\n\n{md}"
            sections.append(body)
            deals_out.append(_deal_row(did, slip_f, True, body, ""))
        else:
            print(f"[ForecastSpecialist] LLM failed for {did}: {err}")
            deals_out.append(_deal_row(did, slip_f, False, "", err))

    markdown = ""
    if sections:
        markdown = f"# Deal health — forecast adjustments\n\nGenerated: {ts}\n\n" + "\n\n---\n\n".join(sections)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(markdown, encoding="utf-8")
        print(f"[ForecastSpecialist] wrote {report_path}")
    msg = f"generated {ok_count}/{len(deals_out)} forecast adjustment(s)"
    print(f"[ForecastSpecialist] {msg}")
    return {
        "success": ok_count > 0,
        "agent": agent,
        "message": msg,
        "handoff_count": len(handoffs),
        "report_path": str(report_path) if sections else None,
        "markdown": markdown,
        "deals": deals_out,
    }
