from __future__ import annotations

import os

from openai import OpenAI


def search(query: str, model: str) -> dict:
    """Run a live web search via the OpenAI Responses API web_search tool."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"success": False, "text": "", "message": "OPENAI_API_KEY not set"}
    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model,
            tools=[{"type": "web_search"}],
            input=query,
        )
        text = getattr(response, "output_text", "") or ""
        if not text:
            return {"success": False, "text": "", "message": "Empty web search response"}
        return {"success": True, "text": text, "message": "ok"}
    except Exception as exc:
        return {"success": False, "text": "", "message": str(exc)}
