from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from exa_py import Exa


def search(query: str, max_results: int, days_back: int) -> dict:
    """Run a live Exa neural search and return snippet-bearing results."""
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        return {"success": False, "results": [], "message": "EXA_API_KEY not set"}
    try:
        start = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
        response = Exa(api_key=api_key).search(
            query,
            num_results=max_results,
            start_published_date=start,
            contents={"highlights": True, "text": {"max_characters": 1500}},
        )
        results = []
        for item in response.results or []:
            highlights = getattr(item, "highlights", None) or []
            text = getattr(item, "text", None) or ""
            snippet = " ".join(highlights) if highlights else text
            results.append(
                {
                    "title": getattr(item, "title", "") or "",
                    "url": getattr(item, "url", "") or "",
                    "snippet": snippet,
                }
            )
        if not results:
            return {"success": False, "results": [], "message": "Empty Exa search response"}
        return {"success": True, "results": results, "message": "ok"}
    except Exception as exc:
        return {"success": False, "results": [], "message": str(exc)}
