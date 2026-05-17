"""Reject user queries that match guardrails.blocked_topics (substring, case-insensitive)."""

import yaml
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_company_config(root: Path) -> dict:
    path = root / "company_config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def check_topic_boundary(query: str, root: Path | None = None) -> dict:
    # v1 substring keeps implementation tiny; expand to token rules if false positives appear.
    base = root if root is not None else _repo_root()
    q = (query or "").lower()
    try:
        topics = load_company_config(base).get("guardrails", {}).get("blocked_topics", [])
    except (OSError, TypeError, yaml.YAMLError) as e:
        print(f"[TopicBoundary] config read failed: {e}")
        return {"allowed": True, "message": str(e), "matched_topic": None}
    for raw in topics:
        t = str(raw).lower().strip()
        if t and t in q:
            print(f"[TopicBoundary] blocked topic match: {raw!r}")
            return {
                "allowed": False,
                "message": "query matched disallowed topic",
                "matched_topic": str(raw),
            }
    return {"allowed": True, "message": "", "matched_topic": None}
