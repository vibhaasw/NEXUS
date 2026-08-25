from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from json import JSONDecodeError
from typing import Any

from ollama import Client, ResponseError

from dispatch.prompts import TASK_CLASSIFIER_SYSTEM_PROMPT

LOGGER = logging.getLogger(__name__)

_TASK_TYPES = {"code", "reasoning", "creative", "vision", "fast_lookup", "long_context"}
_COMPLEXITIES = {"low", "medium", "high"}
_CAPABILITIES = {"code", "reasoning", "vision", "long_context", "fast", "creative"}
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass(slots=True)
class ClassificationResult:
    task_type: str
    complexity: str
    capabilities_required: list[str]
    simplified_prompt: str
    suggested_provider: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    used_fallback: bool = False


def default_classification(request: str) -> ClassificationResult:
    # Low complexity so a classifier hiccup never forces auto-delegation.
    return ClassificationResult(
        task_type="reasoning",
        complexity="low",
        capabilities_required=[],
        simplified_prompt=request.strip(),
        suggested_provider=None,
        used_fallback=True,
    )


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip()).strip()


def parse_classification_payload(payload: str, request: str) -> ClassificationResult:
    cleaned = _strip_fences(payload or "")
    if not cleaned:
        return default_classification(request)

    try:
        parsed = json.loads(cleaned)
    except JSONDecodeError:
        LOGGER.warning("Classifier returned malformed JSON; using fallback defaults")
        return default_classification(request)

    if not isinstance(parsed, dict):
        return default_classification(request)

    task_type = parsed.get("task_type", "reasoning")
    if task_type not in _TASK_TYPES:
        task_type = "reasoning"

    complexity = parsed.get("complexity", "medium")
    if complexity not in _COMPLEXITIES:
        complexity = "medium"

    capabilities_raw = parsed.get("capabilities_required", [])
    capabilities: list[str] = []
    if isinstance(capabilities_raw, list):
        capabilities = [c for c in capabilities_raw if isinstance(c, str) and c in _CAPABILITIES]

    simplified = parsed.get("simplified_prompt", "")
    if not isinstance(simplified, str) or not simplified.strip():
        simplified = request.strip()

    suggested = parsed.get("suggested_provider")
    if suggested is not None and not isinstance(suggested, str):
        suggested = None

    return ClassificationResult(
        task_type=task_type,
        complexity=complexity,
        capabilities_required=capabilities,
        simplified_prompt=simplified.strip(),
        suggested_provider=suggested,
        raw=parsed,
        used_fallback=False,
    )


class TaskClassifier:
    def __init__(self, client: Client, model: str) -> None:
        self._client = client
        self._model = model

    def classify(self, request: str) -> ClassificationResult:
        try:
            response = self._client.chat(
                model=self._model,
                format="json",
                messages=[
                    {"role": "system", "content": TASK_CLASSIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": request},
                ],
            )
        except (ConnectionError, ResponseError) as exc:
            LOGGER.warning("Classifier LLM call failed (%s); using fallback defaults", exc)
            result = default_classification(request)
            result.raw = {"error": str(exc)}
            return result

        content = response.message.content if response.message else ""
        return parse_classification_payload(content or "", request)
