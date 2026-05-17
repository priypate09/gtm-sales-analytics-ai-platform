"""Remove email and phone substrings when guardrails.pii_patterns enables those toggles."""

import re
import yaml
from pathlib import Path

# Practical patterns for outbound LLM prompts; toggles live in company_config.yaml.
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}\b")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_company_config(root: Path) -> dict:
    path = root / "company_config.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def redact_pii(text: str, root: Path | None = None) -> dict:
    # Phone regex requires separators so bare deal IDs do not vanish.
    base = root if root is not None else _repo_root()
    try:
        cfg = load_company_config(base)
        toggles = {str(x).lower().strip() for x in cfg.get("guardrails", {}).get("pii_patterns", [])}
    except (OSError, TypeError, yaml.YAMLError) as e:
        print(f"[PIIFilter] config read failed: {e}")
        return {"sanitized_text": text, "redacted": False, "types": [], "message": str(e)}
    out = text or ""
    types = []
    if "email" in toggles:
        nxt, n = EMAIL_RE.subn("[REDACTED_EMAIL]", out)
        if n:
            types.append("email")
            out = nxt
    if "phone" in toggles:
        nxt, n = PHONE_RE.subn("[REDACTED_PHONE]", out)
        if n:
            types.append("phone")
            out = nxt
    if types:
        print(f"[PIIFilter] redacted: {', '.join(types)}")
    return {
        "sanitized_text": out,
        "redacted": bool(types),
        "types": types,
        "message": f"redacted {', '.join(types)}" if types else "",
    }
