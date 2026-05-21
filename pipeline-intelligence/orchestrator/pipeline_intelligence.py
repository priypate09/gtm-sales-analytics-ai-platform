"""Run guardrails, agents, scoring, optional forecast handoff, and write the deal health report."""

from datetime import datetime, timezone
from pathlib import Path

import yaml

from agents.activity_signal_agent import run_activity_signal_agent
from agents.deal_intel_agent import run_deal_intel_agent
from agents.forecast_specialist_agent import run_forecast_specialist_agent
from agents.pipeline_data_agent import run_pipeline_data_agent
from agents.sentiment_agent import run_sentiment_agent
from guardrails.pii_filter import redact_pii
from guardrails.topic_boundary import check_topic_boundary


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_company_config(root: Path) -> dict:
    path = root / "company_config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _index_deals(agent_result: dict) -> dict:
    return {str(d["deal_id"]): d for d in agent_result.get("deals", []) if d.get("deal_id")}


def compute_scores(act: dict | None, sent: dict | None, w_eng: float, w_sent: float, w_rec: float) -> tuple[float, float]:
    # slip_risk is inverse health so one formula drives both orchestrator and handoff gate.
    eng = float(act.get("engagement_score", 0)) if act else 0.0
    gap = bool(act.get("activity_gap_flag", True)) if act else True
    sent_s = float(sent.get("sentiment_score", 0)) if sent else 0.0
    sent_norm = (sent_s + 1.0) / 2.0
    recency = 0.0 if gap else 1.0
    health = w_eng * eng + w_sent * sent_norm + w_rec * recency
    health = max(0.0, min(1.0, health))
    return health, max(0.0, min(1.0, 1.0 - health))


def build_health_report_markdown(query: str, rows: list, trigger: float, forecast_md: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Deal health report",
        "",
        f"Generated: {ts}",
        f"Query: {query}",
        "",
        "## Pipeline health summary",
        "",
        "| deal_id | account | stage | health | slip | activity_gap | sentiment_decline | handoff |",
        "| --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for r in rows:
        opp = r.get("opportunity") or {}
        act = r.get("activity") or {}
        sent = r.get("sentiment") or {}
        lines.append(
            f"| {r['deal_id']} | {opp.get('account_name', '')} | {opp.get('stage', '')} | "
            f"{r['deal_health_score']:.2f} | {r['slip_risk_score']:.2f} | "
            f"{act.get('activity_gap_flag', '')} | {sent.get('sentiment_decline_flag', '')} | "
            f"{r.get('handoff_triggered', False)} |"
        )
    lines.extend(["", "## Forecast adjustments", ""])
    lines.append(forecast_md if forecast_md.strip() else "_No handoffs — slip risk at or below threshold._")
    return "\n".join(lines)


def run_pipeline_intelligence(query: str, root: Path | None = None) -> dict:
    agent = "pipeline_intelligence"
    base = root if root is not None else _repo_root()
    topic = check_topic_boundary(query, base)
    if not topic.get("allowed", True):
        msg = topic.get("message") or "query blocked by topic boundary"
        print(f"[PipelineIntelligence] {msg}")
        return {
            "success": False,
            "agent": agent,
            "message": msg,
            "query": query,
            "topic_allowed": False,
            "matched_topic": topic.get("matched_topic"),
            "handoff_trigger": None,
            "deals": [],
            "forecast": None,
            "report_markdown": "",
            "report_path": None,
        }

    try:
        config = load_company_config(base)
        trigger = float(config["scoring"]["handoff_trigger"])
        w = config["scoring"]["deal_health_weights"]
        w_eng, w_sent, w_rec = float(w["engagement"]), float(w["sentiment"]), float(w["activity_recency"])
        report_path = (base / config["paths"]["outputs"]["deal_health_report"]).resolve()
    except (KeyError, TypeError, ValueError, OSError) as e:
        msg = f"config error: {e}"
        print(f"[PipelineIntelligence] {msg}")
        return {
            "success": False,
            "agent": agent,
            "message": msg,
            "query": query,
            "topic_allowed": True,
            "matched_topic": None,
            "handoff_trigger": None,
            "deals": [],
            "forecast": None,
            "report_markdown": "",
            "report_path": None,
        }

    print(f"[PipelineIntelligence] topic ok; running pipeline")
    pipe = run_pipeline_data_agent(base)
    if not pipe.get("success"):
        msg = pipe.get("message", "pipeline data failed")
        print(f"[PipelineIntelligence] {msg}")
        return {
            "success": False,
            "agent": agent,
            "message": msg,
            "query": query,
            "topic_allowed": True,
            "matched_topic": None,
            "handoff_trigger": trigger,
            "deals": [],
            "forecast": None,
            "report_markdown": "",
            "report_path": None,
        }

    deal_ids = list(pipe.get("deal_ids") or [])
    opp_by_id = {str(o["deal_id"]): o for o in pipe.get("opportunities") or []}
    intel = run_deal_intel_agent(deal_ids, base)
    activity = run_activity_signal_agent(deal_ids, base)
    sentiment = run_sentiment_agent(deal_ids, base)
    intel_by = _index_deals(intel)
    act_by = _index_deals(activity)
    sent_by = _index_deals(sentiment)

    rows, handoffs = [], []
    for did in deal_ids:
        opp = opp_by_id.get(did, {"deal_id": did})
        act, sent = act_by.get(did), sent_by.get(did)
        health, slip = compute_scores(act, sent, w_eng, w_sent, w_rec)
        intel_row = intel_by.get(did) or {}
        rag_raw = str(intel_row.get("context_block") or "")
        rag_red = redact_pii(rag_raw, base).get("sanitized_text", rag_raw)
        triggered = slip > trigger
        rows.append(
            {
                "deal_id": did,
                "opportunity": opp,
                "deal_health_score": health,
                "slip_risk_score": slip,
                "handoff_triggered": triggered,
                "activity": act or {},
                "sentiment": sent or {},
                "deal_intel_ok": bool(intel_row.get("retrieval_ok")),
                "rag_summary_redacted": rag_red,
            }
        )
        if triggered:
            handoffs.append(
                {
                    "deal_id": did,
                    "slip_risk_score": slip,
                    "opportunity": opp,
                    "signals": {
                        "deal_health_score": health,
                        "engagement_score": (act or {}).get("engagement_score"),
                        "activity_gap_flag": (act or {}).get("activity_gap_flag"),
                        "days_since_last": (act or {}).get("days_since_last"),
                        "activity_count": (act or {}).get("activity_count"),
                        "sentiment_score": (sent or {}).get("sentiment_score"),
                        "tone_trajectory": (sent or {}).get("tone_trajectory"),
                        "sentiment_decline_flag": (sent or {}).get("sentiment_decline_flag"),
                    },
                    "rag_summary": rag_red,
                }
            )

    forecast = run_forecast_specialist_agent(handoffs, base) if handoffs else None
    forecast_md = (forecast or {}).get("markdown") or ""
    report_md = build_health_report_markdown(query, rows, trigger, forecast_md)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")
    print(f"[PipelineIntelligence] wrote {report_path}")

    n_handoff = len(handoffs)
    msg = f"scored {len(rows)} deal(s), {n_handoff} handoff(s)"
    print(f"[PipelineIntelligence] {msg}")
    return {
        "success": True,
        "agent": agent,
        "message": msg,
        "query": query,
        "topic_allowed": True,
        "matched_topic": None,
        "handoff_trigger": trigger,
        "deals": rows,
        "forecast": forecast,
        "report_markdown": report_md,
        "report_path": str(report_path),
    }
