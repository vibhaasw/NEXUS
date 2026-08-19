from __future__ import annotations

from typing import Any

from ollama import Client, ResponseError

from handlers.base import BaseHandler, HandlerResult


class QAHandler(BaseHandler):
    """Handles general knowledge questions and conversational chat via Ollama."""

    def __init__(self, client: Client, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def name(self) -> str:
        return "answer_question"

    @property
    def description(self) -> str:
        return (
            "Answer a general knowledge question, have a conversation, explain a concept, "
            "or respond to any query that does NOT require opening an app, editing a file, "
            "searching the web, or writing code."
        )

    def tool_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The user's question or conversational message to answer directly.",
                },
            },
            "required": ["question"],
        }

    def execute(self, **kwargs: Any) -> HandlerResult:
        question = kwargs.get("question", "")
        if not question.strip():
            return HandlerResult(success=False, output="No question provided.", handler_name=self.name)

        try:
            response = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a helpful voice assistant. Be concise and direct."},
                    {"role": "user", "content": question},
                ],
            )
        except (ConnectionError, ResponseError) as exc:
            return HandlerResult(success=False, output=f"LLM error: {exc}", handler_name=self.name)

        content = response.message.content if response.message else ""
        return HandlerResult(
            success=True,
            output=content.strip() or "No response generated.",
            handler_name=self.name,
            raw_args=kwargs,
        )
