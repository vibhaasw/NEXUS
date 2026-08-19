from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class HandlerResult:
    success: bool
    output: str
    handler_name: str
    raw_args: dict[str, Any] = field(default_factory=dict)


class BaseHandler(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Short snake_case identifier matching the Ollama tool function name."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description shown to the LLM as the tool docstring."""

    @abstractmethod
    def tool_parameters(self) -> dict[str, Any]:
        """JSON Schema for the function parameters the LLM should produce."""

    @abstractmethod
    def execute(self, **kwargs: Any) -> HandlerResult:
        """Run the action. kwargs come from the LLM tool-call arguments."""

    def as_ollama_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.tool_parameters(),
            },
        }


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, BaseHandler] = {}

    def register(self, handler: BaseHandler) -> None:
        self._handlers[handler.name] = handler

    def get(self, name: str) -> BaseHandler | None:
        return self._handlers.get(name)

    def all_handlers(self) -> list[BaseHandler]:
        return list(self._handlers.values())

    def ollama_tools(self) -> list[dict[str, Any]]:
        return [h.as_ollama_tool() for h in self._handlers.values()]

    def handler_names(self) -> list[str]:
        return list(self._handlers.keys())
