"""Deal intel from scoped RAG retrieval only; no LLM in this module."""

import yaml
from pathlib import Path

from rag.retriever import retrieve

RAG_QUERIES = [
    "Who is involved, what are they trying to achieve, and what are the next steps discussed?",
    "What objections, delays, budget concerns, or technical risks were mentioned?",
    "What was said about timeline, procurement, legal, or the customer's decision process?",
]


def _repo_root() -> Path:
    # pipeline-intelligence root for config and consistent retrieve(root).
    return Path(__file__).resolve().parent.parent


def load_company_config(root: Path) -> dict:
    path = root / "company_config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _merge_hits(query_results: list[dict], max_chunks: int) -> tuple[str, list[dict]]:
    # Dedupe chunk ids across queries so the same turn is not repeated in context_block.
    best = {}
    for qr in query_results:
        if not qr.get("success"):
            continue
        for h in qr.get("hits", []):
            hid = h.get("id")
            if hid is None:
                continue
            dist = h.get("distance")
            if hid not in best:
                best[hid] = h
            else:
                old = best[hid].get("distance")
                if dist is not None and (old is None or dist < old):
                    best[hid] = h
    merged = list(best.values())
    # sort ascending by distance; None distances last
    merged.sort(key=lambda x: (x.get("distance") is None, x.get("distance") if x.get("distance") is not None else 1e9))
    merged = merged[:max_chunks]
    parts = []
    for h in merged:
        doc = h.get("document")
        if doc:
            parts.append(str(doc).strip())
    return "\n\n".join(parts), merged


def run_deal_intel_agent(deal_ids: list[str], root: Path | None = None) -> dict:
    # Run fixed RAG queries per deal; one bad deal does not abort the rest of the batch.
    agent = "deal_intel_agent"
    bad_input = {
        "success": False,
        "agent": agent,
        "message": "deal_ids must be a non-empty list",
        "deals": [],
    }
    if not deal_ids:
        print(f"[DealIntelAgent] {bad_input['message']}")
        return bad_input

    base = root if root is not None else _repo_root()
    try:
        cfg = load_company_config(base)
        max_chunks = len(RAG_QUERIES) * int(cfg["rag"]["top_k"])
    except (KeyError, TypeError, ValueError, OSError) as e:
        msg = f"config error: {e}"
        print(f"[DealIntelAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}

    deals_out = []
    seen_any = False
    for raw_id in deal_ids:
        did = str(raw_id).strip()
        if not did:
            print("[DealIntelAgent] skipping blank deal_id")
            continue
        seen_any = True
        query_results = []
        for q in RAG_QUERIES:
            r = retrieve(did, q, base)
            query_results.append(
                {
                    "query": q,
                    "success": r["success"],
                    "message": r["message"],
                    "hits": r.get("hits", []),
                }
            )
        retrieval_ok = all(qr["success"] for qr in query_results)
        context_block, merged = _merge_hits(query_results, max_chunks)
        if not merged:
            print(f"[DealIntelAgent] no chunks for deal_id={did}")
        deals_out.append(
            {
                "deal_id": did,
                "retrieval_ok": retrieval_ok,
                "query_results": query_results,
                "context_block": context_block,
            }
        )

    if not seen_any:
        msg = "no valid deal_ids after stripping"
        print(f"[DealIntelAgent] {msg}")
        return {"success": False, "agent": agent, "message": msg, "deals": []}

    msg = f"processed {len(deals_out)} deal(s) with {len(RAG_QUERIES)} queries each"
    print(f"[DealIntelAgent] {msg}")
    return {
        "success": True,
        "agent": agent,
        "message": msg,
        "deals": deals_out,
    }
