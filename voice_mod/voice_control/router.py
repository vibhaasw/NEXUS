from __future__ import annotations

import json
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Any

from voice_control.llm import OllamaRouterClient
from voice_control.prompts import ROUTER_SYSTEM_PROMPT


@dataclass(slots=True)
class RoutedResponse:
    mode: str
    reply: str
    command_name: str | None = None
    command_args: dict[str, Any] = field(default_factory=dict)
    raw_payload: str = ""


class IntentRouter:
    def __init__(self, llm_client: OllamaRouterClient) -> None:
        self._llm_client = llm_client

    def route(self, transcript: str) -> RoutedResponse:
        llm_response = self._llm_client.route(ROUTER_SYSTEM_PROMPT, transcript)
        return parse_router_payload(llm_response.content)


def parse_router_payload(payload: str) -> RoutedResponse:
    raw_payload = payload or ""
    try:
        parsed = json.loads(raw_payload)
    except JSONDecodeError:
        return RoutedResponse(
            mode="assistant",
            reply=raw_payload.strip() or "I could not classify that request.",
            raw_payload=raw_payload,
        )

    mode = parsed.get("mode", "assistant")
    if mode not in {"assistant", "command"}:
        mode = "assistant"

    command_name = parsed.get("command_name")
    command_args = parsed.get("command_args") or {}
    if not isinstance(command_args, dict):
        command_args = {"value": command_args}

    reply = str(parsed.get("reply", "")).strip() or "I processed your request."
    return RoutedResponse(
        mode=mode,
        reply=reply,
        command_name=command_name,
        command_args=command_args,
        raw_payload=raw_payload,
    )
