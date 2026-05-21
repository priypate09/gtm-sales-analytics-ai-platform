"""Index synthetic Gong transcripts and email threads into Chroma per deal_id."""

import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rag.embedder import upsert_documents


def main() -> None:
    cfg = yaml.safe_load((ROOT / "company_config.yaml").read_text(encoding="utf-8"))
    path_g = (ROOT / cfg["paths"]["synthetic"]["gong_transcripts"]).resolve()
    path_e = (ROOT / cfg["paths"]["synthetic"]["email_threads"]).resolve()
    transcripts = json.loads(path_g.read_text(encoding="utf-8"))
    emails = pd.read_csv(path_e, encoding="utf-8", encoding_errors="replace")
    by_tx: dict[str, list] = {}
    for row in transcripts:
        did = str(row["deal_id"]).strip()
        by_tx.setdefault(did, []).append(row)
    deal_ids = sorted(set(by_tx) | set(emails["deal_id"].astype(str).str.strip()))
    total = 0
    for did in deal_ids:
        ids, texts, metas = [], [], []
        for i, row in enumerate(by_tx.get(did, [])):
            ids.append(f"{did}:transcript:{i}")
            texts.append(str(row.get("turn_text", "")))
            metas.append({"deal_id": did})
        sub = emails[emails["deal_id"].astype(str).str.strip() == did]
        for i, (_, row) in enumerate(sub.iterrows()):
            ids.append(f"{did}:email:{i}")
            texts.append(str(row.get("body", "")))
            metas.append({"deal_id": did})
        if not ids:
            continue
        out = upsert_documents(ids, texts, metas, ROOT)
        if not out.get("success"):
            print(f"[IndexRAG] failed deal_id={did}: {out.get('message')}")
            sys.exit(1)
        total += int(out.get("upserted", 0))
        print(f"[IndexRAG] indexed {did}: {out.get('upserted')} chunks")
    print(f"[IndexRAG] done: {total} chunks across {len(deal_ids)} deal(s)")


if __name__ == "__main__":
    main()
