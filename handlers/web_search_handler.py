from __future__ import annotations

import webbrowser
from typing import Any

from handlers.base import BaseHandler, HandlerResult


class WebSearchHandler(BaseHandler):
    """Opens a web search in the default browser."""

    @property
    def name(self) -> str:
        return "search_web"

    @property
    def description(self) -> str:
        return (
            "Search the web for something. Use when the user asks to look up, search, "
            "google, or find information online."
        )

    def tool_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up on the web.",
                },
            },
            "required": ["query"],
        }

    def execute(self, **kwargs: Any) -> HandlerResult:
        query = kwargs.get("query", "")
        if not query.strip():
            return HandlerResult(success=False, output="No search query provided.", handler_name=self.name)

        from urllib.parse import quote_plus
        url = f"https://www.google.com/search?q={quote_plus(query)}"

        try:
            webbrowser.open(url)
            return HandlerResult(
                success=True,
                output=f"Opened web search for: {query}",
                handler_name=self.name,
                raw_args=kwargs,
            )
        except Exception as exc:
            return HandlerResult(
                success=False,
                output=f"Failed to open browser: {exc}",
                handler_name=self.name,
            )
