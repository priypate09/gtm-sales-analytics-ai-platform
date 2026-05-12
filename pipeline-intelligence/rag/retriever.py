"""Semantic retrieval from Chroma scoped by deal_id metadata."""

from pathlib import Path

from rag.embedder import encode_texts, get_chroma_collection, load_company_config, repo_root


def _fail(msg: str, deal_id: str, query: str) -> dict:
    print(f"[RAGRetriever] {msg}")
    return {"success": False, "message": msg, "deal_id": deal_id, "query": query, "hits": []}


def retrieve(
    deal_id: str,
    query: str,
    root: Path | None = None,
    top_k: int | None = None,
) -> dict:
    # Query embeddings restricted to one deal via Chroma where filter only.
    if not deal_id or not str(deal_id).strip():
        return _fail("deal_id is required", deal_id, query)
    if not query or not str(query).strip():
        return _fail("query is required", deal_id, query)

    did = str(deal_id).strip()
    qtxt = str(query).strip()
    base = root if root is not None else repo_root()

    try:
        cfg = load_company_config(base)
        k = int(top_k) if top_k is not None else int(cfg["rag"]["top_k"])
        if k < 1:
            k = 1
    except (KeyError, TypeError, ValueError) as e:
        return _fail(f"config error: {e}", deal_id, query)

    try:
        qemb = encode_texts([qtxt], base)
        col = get_chroma_collection(base)
        raw = col.query(
            query_embeddings=qemb,
            n_results=k,
            where={"deal_id": did},
        )
    except Exception as e:
        return _fail(f"query failed: {e}", deal_id, query)

    hits = []
    ids_batch = raw.get("ids") or []
    docs_batch = raw.get("documents") or []
    meta_batch = raw.get("metadatas") or []
    dist_batch = raw.get("distances") or []
    row_ids = ids_batch[0] if ids_batch else []
    row_docs = docs_batch[0] if docs_batch else []
    row_meta = meta_batch[0] if meta_batch else []
    row_dist = dist_batch[0] if dist_batch else []
    for i in range(len(row_ids)):
        hits.append(
            {
                "id": row_ids[i],
                "document": row_docs[i] if i < len(row_docs) else None,
                "metadata": row_meta[i] if i < len(row_meta) else {},
                "distance": row_dist[i] if i < len(row_dist) else None,
            }
        )

    msg = f"{len(hits)} hits for deal_id={did}"
    print(f"[RAGRetriever] {msg}")
    return {
        "success": True,
        "message": msg,
        "deal_id": did,
        "query": qtxt,
        "hits": hits,
    }
