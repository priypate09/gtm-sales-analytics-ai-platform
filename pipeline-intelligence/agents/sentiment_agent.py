"""Buyer tone trajectory from Gong buyer turns plus email threads (lexicon early vs late by call_num)."""

import json
import yaml
import pandas as pd
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_company_config(root: Path) -> dict:
    path = root / "company_config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def lexicon_score(text: str, positive_words: list, negative_words: list) -> float:
    # partial match handles inflected words (e.g. "excited" matches "excite")
    t = (text or "").lower()
    pos = sum(t.count(w.lower()) for w in positive_words)
    neg = sum(t.count(w.lower()) for w in negative_words)
    tot = pos + neg
    return (pos - neg) / tot if tot else 0.0


def score_one_deal(
    deal_id: str,
    records: list,
    email_df: pd.DataFrame,
    positive_words: list,
    negative_words: list,
    decline_threshold: float,
) -> dict:
    # Cutoff uses every call row for the deal so email split matches pipeline calendar reality.
    rows_all = [r for r in records if str(r.get("deal_id", "")).strip() == deal_id]
    cutoff_date = None
    if rows_all:
        dts = pd.to_datetime([r.get("call_date") for r in rows_all], errors="coerce")
        if dts.notna().any():
            cutoff_date = dts.max().date()
    buyer = [r for r in rows_all if "buyer" in str(r.get("speaker", "")).lower()]
    nums = []
    for r in buyer:
        try:
            nums.append(int(r["call_num"]))
        except (KeyError, ValueError, TypeError):
            pass
    nums = sorted(set(nums))

    if not nums:
        early_c, late_c = "", ""
    elif len(nums) == 1:
        sub = [r for r in buyer if int(r["call_num"]) in {nums[0]}]
        sub.sort(key=lambda x: (str(x.get("call_date", "")), int(x.get("call_num", 0)), int(x.get("turn_num", 0))))
        s = " ".join(str(r.get("turn_text", "")) for r in sub)
        early_c, late_c = s, s
    else:
        k = len(nums) // 2
        sub_e_b = [r for r in buyer if int(r["call_num"]) in set(nums[:k])]
        sub_e_b.sort(key=lambda x: (str(x.get("call_date", "")), int(x.get("call_num", 0)), int(x.get("turn_num", 0))))
        early_c = " ".join(str(r.get("turn_text", "")) for r in sub_e_b)
        sub_l_b = [r for r in buyer if int(r["call_num"]) in set(nums[k:])]
        sub_l_b.sort(key=lambda x: (str(x.get("call_date", "")), int(x.get("call_num", 0)), int(x.get("turn_num", 0))))
        late_c = " ".join(str(r.get("turn_text", "")) for r in sub_l_b)
    sub_e = email_df[email_df["deal_id"].astype(str).str.strip() == deal_id]
    early_e, late_e = [], []
    for _, row in sub_e.iterrows():
        body, ts = str(row.get("body", "")), pd.to_datetime(row.get("timestamp"), errors="coerce")
        if cutoff_date is None or pd.isna(ts) or ts.date() > cutoff_date:
            late_e.append(body)
        else:
            early_e.append(body)
    early_txt = (early_c + " " + " ".join(early_e)).strip()
    late_txt = (late_c + " " + " ".join(late_e)).strip()
    early_s = lexicon_score(early_txt, positive_words, negative_words)
    late_s = lexicon_score(late_txt, positive_words, negative_words)
    traj = late_s - early_s
    date_sigs = []
    for r in buyer:
        cd = r.get("call_date")
        if cd is not None and str(cd).strip():
            date_sigs.append(str(cd).strip())
    for _, row in sub_e.iterrows():
        ts = row.get("timestamp")
        if ts is not None and str(ts).strip():
            date_sigs.append(str(ts).strip())
    first_at = min(date_sigs) if date_sigs else None
    last_at = max(date_sigs) if date_sigs else None
    return {
        "deal_id": deal_id,
        "sentiment_score": late_s,
        "tone_trajectory": traj,
        "sentiment_decline_flag": traj < decline_threshold,
        "window_count": 2,
        "buyer_turn_count": len(buyer),
        "email_count": int(len(sub_e)),
        "first_signal_at": first_at,
        "last_signal_at": last_at,
    }


def run_sentiment_agent(deal_ids: list[str], root: Path | None = None) -> dict:
    agent = "sentiment_agent"
    if not deal_ids:
        msg = "deal_ids must be a non-empty list"
        print(f"[SentimentAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}
    base = root if root is not None else _repo_root()
    try:
        config = load_company_config(base)
        rel_g = config["paths"]["sample"]["gong_transcripts"]
        rel_e = config["paths"]["sample"]["email_threads"]
        thr = float(config["scoring"]["sentiment_decline_threshold"])
        pos = list(config["scoring"]["sentiment"]["positive_words"])
        neg = list(config["scoring"]["sentiment"]["negative_words"])
        path_g = (base / rel_g).resolve()
        path_e = (base / rel_e).resolve()
    except (KeyError, TypeError, ValueError, OSError) as e:
        msg = f"config or path error: {e}"
        print(f"[SentimentAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}
    if not path_g.is_file() or not path_e.is_file():
        msg = f"missing data file: {path_g} or {path_e}"
        print(f"[SentimentAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}
    try:
        records = json.loads(path_g.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("gong_transcripts must be a JSON array")
        df = pd.read_csv(path_e, encoding="utf-8", encoding_errors="replace")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, pd.errors.ParserError) as e:
        msg = f"read failed: {e}"
        print(f"[SentimentAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}
    need = {"deal_id", "body", "timestamp"}
    miss = need - set(df.columns)
    if miss:
        msg = f"email_threads missing columns: {', '.join(sorted(miss))}"
        print(f"[SentimentAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}
    requested = [str(x).strip() for x in deal_ids if str(x).strip()]
    if not requested:
        msg = "no valid deal_ids after stripping"
        print(f"[SentimentAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}
    deals_out = [score_one_deal(did, records, df, pos, neg, thr) for did in requested]
    msg = f"scored {len(deals_out)} deal(s) from {rel_g} + {rel_e}"
    print(f"[SentimentAgent] {msg}")
    return {"success": True, "agent": agent, "message": msg, "deals": deals_out}
