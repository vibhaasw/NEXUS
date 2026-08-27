from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from ollama import Client, ResponseError

from handlers.base import HandlerRegistry, HandlerResult
from dispatch.classifier import TaskClassifier
from dispatch.routing_policy import (
    looks_like_local_action,
    parse_local_action,
    prefers_local_answer,
    routing_hint,
    should_auto_delegate,
)
from voice_control.prompts import ROUTER_SYSTEM_PROMPT

LOGGER = logging.getLogger(__name__)

_TEXT_TOOL_CALL_RE = re.compile(
    r"(\w+)\s*\(\s*(\{.*?\})\s*\)|(\w+)\s+(\{.*\})",
    re.DOTALL,
)

_NAME_KEYS = ("name", "type", "function")
_ARGS_KEYS = ("arguments", "parameters", "params", "args")


def _extract_from_json_obj(obj: dict[str, Any], registry: HandlerRegistry) -> tuple[str, dict[str, Any]] | None:
    name = None
    for k in _NAME_KEYS:
        val = obj.get(k)
        if isinstance(val, str) and registry.get(val):
            name = val
            break
    if not name:
        return None

    args: dict[str, Any] = {}
    for k in _ARGS_KEYS:
        val = obj.get(k)
        if isinstance(val, dict):
            args = val
            break
    return name, args


def _try_parse_text_tool_call(text: str, registry: HandlerRegistry) -> tuple[str, dict[str, Any]] | None:
    stripped = text.strip()

    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    result = _extract_from_json_obj(item, registry)
                    if result:
                        return result
        elif isinstance(parsed, dict):
            result = _extract_from_json_obj(parsed, registry)
            if result:
                return result
    except json.JSONDecodeError:
        pass

    m = _TEXT_TOOL_CALL_RE.search(text)
    if m:
        name = m.group(1) or m.group(3)
        args_str = m.group(2) or m.group(4)
        try:
            args = json.loads(args_str)
            if registry.get(name):
                return name, args
        except json.JSONDecodeError:
            pass

    for handler_name in registry.handler_names():
        if handler_name in text:
            json_match = re.search(r"\{[^{}]*\}", text)
            if json_match:
                try:
                    args = json.loads(json_match.group())
                    return handler_name, args
                except json.JSONDecodeError:
                    continue

    return None


@dataclass(slots=True)
class RoutedResponse:
    handler_name: str
    reply: str
    success: bool
    raw_args: dict[str, Any] = field(default_factory=dict)
    raw_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    auto_delegated: bool = False


class IntentRouter:
    def __init__(self, client: Client, model: str, registry: HandlerRegistry) -> None:
        self._client = client
        self._model = model
        self._registry = registry
        self._classifier = TaskClassifier(client, model)

    def route(self, transcript: str) -> RoutedResponse:
        local = parse_local_action(transcript)
        if local:
            fn_name, fn_args = local
            handler = self._registry.get(fn_name)
            if handler:
                LOGGER.info("Fast-path local action: %s(%s)", fn_name, fn_args)
                result = handler.execute(**fn_args)
                return RoutedResponse(
                    handler_name=result.handler_name,
                    reply=result.output,
                    success=result.success,
                    raw_args=result.raw_args,
                    auto_delegated=False,
                )

        # Machine-action phrasing must never fall through to cloud auto-delegate.
        if looks_like_local_action(transcript):
            open_handler = self._registry.get("open_app")
            if open_handler and re.search(r"\b(?:open|launch)\b", transcript, re.IGNORECASE):
                # Last-resort: strip to likely app token(s).
                cleaned = re.sub(
                    r".*?\b(?:open|launch)\b",
                    "",
                    transcript,
                    count=1,
                    flags=re.IGNORECASE,
                )
                cleaned = re.sub(
                    r"\b(the|a|an|my|app|application|please|for me|now)\b",
                    " ",
                    cleaned,
                    flags=re.IGNORECASE,
                )
                cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,\"'!?")
                if cleaned:
                    LOGGER.info("Local-action fallback open_app(%s)", cleaned)
                    result = open_handler.execute(target=cleaned)
                    return RoutedResponse(
                        handler_name=result.handler_name,
                        reply=result.output,
                        success=result.success,
                        raw_args=result.raw_args,
                        auto_delegated=False,
                    )

        classification = self._classifier.classify(transcript)
        LOGGER.info(
            "Classifier: type=%s complexity=%s capabilities=%s suggested=%s",
            classification.task_type,
            classification.complexity,
            classification.capabilities_required,
            classification.suggested_provider,
        )

        # Clear local Q&A: skip tool-calling so we don't mis-route facts to search_web.
        if (
            prefers_local_answer(classification)
            and classification.task_type in {"fast_lookup", "reasoning", "creative"}
            and classification.complexity in {"low", "medium"}
            and not looks_like_local_action(transcript)
        ):
            LOGGER.info(
                "Local classifier → answer_question (%s/%s)",
                classification.task_type,
                classification.complexity,
            )
            return self._fallback_qa(transcript, reason="local classifier Q&A")

        # Local model decides the handler. Classifier only tags + hints.
        # Include delegate_to_external_ai only when tags say the task is hard enough.
        tools = self._registry.ollama_tools()
        allow_external = should_auto_delegate(classification)
        if not allow_external:
            tools = [t for t in tools if t.get("function", {}).get("name") != "delegate_to_external_ai"]

        hint = routing_hint(classification)
        user_message = f"Routing hint: {hint}\n\nUser request: {transcript}"
        LOGGER.info(
            "Local router deciding handler (external_allowed=%s, tools=%d)",
            allow_external,
            len(tools),
        )
        LOGGER.debug("Tools: %s", [t.get("function", {}).get("name") for t in tools])

        try:
            response = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                tools=tools,
            )
        except (ConnectionError, ResponseError) as exc:
            return RoutedResponse(
                handler_name="error",
                reply=f"Router LLM call failed: {exc}",
                success=False,
            )

        message = response.message
        if not message:
            return self._fallback_qa(transcript, reason="empty LLM response")

        tool_calls = message.tool_calls or []
        raw_tool_calls = []
        for tc in tool_calls:
            raw_tool_calls.append({
                "name": tc.function.name if tc.function else None,
                "arguments": tc.function.arguments if tc.function else {},
            })

        if tool_calls:
            return self._dispatch_tool_call(
                tool_calls[0].function.name if tool_calls[0].function else None,
                tool_calls[0].function.arguments if tool_calls[0].function else {},
                transcript,
                raw_tool_calls,
            )

        direct_text = (message.content or "").strip()
        if direct_text:
            parsed = _try_parse_text_tool_call(direct_text, self._registry)
            if parsed:
                fn_name, fn_args = parsed
                LOGGER.info("Parsed text-embedded tool call: %s(%s)", fn_name, fn_args)
                return self._dispatch_tool_call(fn_name, fn_args, transcript, raw_tool_calls)

        if direct_text:
            return self._fallback_qa(transcript, reason="no tool call detected in text response")
        return self._fallback_qa(transcript, reason="no tool calls and no text")

    def _dispatch_tool_call(
        self,
        fn_name: str | None,
        fn_args: dict[str, Any],
        transcript: str,
        raw_tool_calls: list[dict[str, Any]],
    ) -> RoutedResponse:
        if not fn_name:
            return self._fallback_qa(transcript, reason="tool call missing function name")

        handler = self._registry.get(fn_name)
        if not handler:
            LOGGER.warning("LLM called unknown tool '%s', falling back to QA", fn_name)
            return self._fallback_qa(transcript, reason=f"unknown tool: {fn_name}")

        LOGGER.info("Dispatching to handler '%s' with args: %s", fn_name, fn_args)
        result: HandlerResult = handler.execute(**fn_args)

        return RoutedResponse(
            handler_name=result.handler_name,
            reply=result.output,
            success=result.success,
            raw_args=result.raw_args,
            raw_tool_calls=raw_tool_calls,
            auto_delegated=fn_name == "delegate_to_external_ai",
        )

    def _fallback_qa(self, transcript: str, reason: str) -> RoutedResponse:
        LOGGER.info("Falling back to QA handler: %s", reason)
        qa = self._registry.get("answer_question")
        if qa:
            result = qa.execute(question=transcript)
            return RoutedResponse(
                handler_name=result.handler_name,
                reply=result.output,
                success=result.success,
                raw_args=result.raw_args,
            )
        return RoutedResponse(
            handler_name="fallback",
            reply="I could not route your request and no QA handler is available.",
            success=False,
        )
