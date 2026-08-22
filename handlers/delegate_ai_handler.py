from __future__ import annotations

from typing import Any

from ollama import Client

from dispatch.orchestrator import AIOrchestrator
from handlers.base import BaseHandler, HandlerResult


class DelegateAIHandler(BaseHandler):
    """Routes complex tasks to external AI providers via the dispatch orchestrator."""

    def __init__(self, client: Client, model: str) -> None:
        self._orchestrator = AIOrchestrator(client, model)

    @property
    def name(self) -> str:
        return "delegate_to_external_ai"

    @property
    def description(self) -> str:
        return (
            "Send the request to the best external AI provider (OpenAI, Gemini, Anthropic, etc.). "
            "Selected automatically by the local classifier for complex reasoning, coding, creative "
            "work, vision, or long-context tasks — the user does not need to ask for external AI."
        )

    def tool_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "The user's task or question to send to an external AI provider.",
                },
            },
            "required": ["request"],
        }

    def execute(self, **kwargs: Any) -> HandlerResult:
        request = kwargs.get("request", "").strip()
        if not request:
            return HandlerResult(
                success=False,
                output="No request provided for external AI dispatch.",
                handler_name=self.name,
            )

        result = self._orchestrator.dispatch(request)
        output = result.output

        if result.switched_accounts > 0:
            output = f"(Switched through {result.switched_accounts} account(s))\n{output}"

        if result.provider_id:
            meta = f"[{result.provider_id}"
            if result.model:
                meta += f" / {result.model}"
            if result.account_label:
                meta += f" / {result.account_label}"
            meta += "]"
            if result.handoff:
                output = f"{meta} {output}"
            else:
                output = f"{meta}\n{output}"

        return HandlerResult(
            success=result.success,
            output=output,
            handler_name=self.name,
            raw_args={
                "request": request,
                "provider_id": result.provider_id,
                "model": result.model,
                "account_label": result.account_label,
                "handoff": result.handoff,
                "local_fallback": result.local_fallback,
                "switched_accounts": result.switched_accounts,
                "attempts": result.attempts,
                "classification": result.classification.raw if result.classification else {},
            },
        )
