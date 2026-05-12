"""Chroma-backed dense embeddings for RAG documents."""

import yaml
import chromadb
from pathlib import Path
from sentence_transformers import SentenceTransformer

_model = None
_model_key = None


def repo_root() -> Path:
    # Resolve pipeline-intelligence root next to rag/ for config and Chroma paths.
    return Path(__file__).resolve().parent.parent


def load_company_config(root: Path) -> dict:
    path = root / "company_config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _sentence_model(root: Path) -> SentenceTransformer:
    # avoid reloading model on every call — expensive download
    global _model, _model_key
    cfg = load_company_config(root)
    key = cfg["rag"]["embedding_model"]
    if _model is None or _model_key != key:
        print(f"[RAGEmbedder] loading embedding model {key}")
        _model = SentenceTransformer(key)
        _model_key = key
    return _model


def encode_texts(texts: list[str], root: Path | None = None) -> list[list[float]]:
    # One embedding per string; caller supplies pre-segmented chunks (e.g. one turn per row).
    if not texts:
        return []
    base = root if root is not None else repo_root()
    model = _sentence_model(base)
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def get_chroma_collection(root: Path | None = None):
    # Persistent Chroma collection shared with retriever for the configured collection name.
    base = root if root is not None else repo_root()
    cfg = load_company_config(base)
    db_path = (base / cfg["paths"]["chroma_db"]).resolve()
    db_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(db_path))
    return client.get_or_create_collection(name=cfg["rag"]["collection_name"])


def upsert_documents(
    ids: list[str],
    texts: list[str],
    metadatas: list[dict],
    root: Path | None = None,
) -> dict:
    # Upsert pre-chunked texts with embeddings and deal_id in every metadata row.
    base = root if root is not None else repo_root()
    n = len(ids)
    if n == 0 or n != len(texts) or n != len(metadatas):
        msg = "ids, texts, and metadatas must be same non-zero length"
        print(f"[RAGEmbedder] {msg}")
        return {"success": False, "message": msg, "upserted": 0}
    for i, meta in enumerate(metadatas):
        if "deal_id" not in meta:
            msg = f"metadatas[{i}] missing deal_id"
            print(f"[RAGEmbedder] {msg}")
            return {"success": False, "message": msg, "upserted": 0}
    try:
        embeddings = encode_texts(texts, base)
        col = get_chroma_collection(base)
        col.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
        msg = f"upserted {n} vectors into {col.name}"
        print(f"[RAGEmbedder] {msg}")
        return {"success": True, "message": msg, "upserted": n}
    except Exception as e:
        msg = f"upsert failed: {e}"
        print(f"[RAGEmbedder] {msg}")
        return {"success": False, "message": msg, "upserted": 0}
