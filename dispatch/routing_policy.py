from __future__ import annotations

import re

from dispatch.classifier import ClassificationResult

_OPEN_RE = re.compile(r"\b(?:open|launch|start|run)\s+(.+)", re.IGNORECASE)
_SEARCH_RE = re.compile(
    r"\b(?:search the web for|search for|google|look up online)\s+(.+)",
    re.IGNORECASE,
)
_EDIT_RE = re.compile(r"\b(?:edit|modify|open file)\s+(.+)", re.IGNORECASE)


def looks_like_local_action(transcript: str) -> bool:
    """True when the user is clearly asking to act on the machine, not ask an AI."""
    lower = transcript.lower()
    return bool(
        _OPEN_RE.search(transcript)
        or _SEARCH_RE.search(transcript)
        or _EDIT_RE.search(transcript)
        or re.search(r"\b(search the web|google|look up online)\b", lower)
    )


def parse_local_action(transcript: str) -> tuple[str, dict[str, str]] | None:
    """
    Fast-path parse for obvious machine actions.
    Returns (handler_name, kwargs) or None.
    """
    if m := _SEARCH_RE.search(transcript):
        return "search_web", {"query": m.group(1).strip(" .")}

    if m := _EDIT_RE.search(transcript):
        return "edit_file", {"file_path": m.group(1).strip(" .")}

    if m := _OPEN_RE.search(transcript):
        return "open_app", {"target": m.group(1).strip(" .")}

    return None


def should_auto_delegate(classification: ClassificationResult) -> bool:
    """
    Decide if this request should go to external AI automatically.
    Uses classifier tags only — the user never has to say 'use external AI'.
    """
    if classification.complexity == "high":
        return True

    if classification.task_type == "vision":
        return True

    if "long_context" in classification.capabilities_required:
        return True

    if classification.task_type in {"code", "reasoning", "creative", "long_context"}:
        if classification.complexity == "medium":
            return True

    if classification.suggested_provider:
        return True

    return False


def routing_hint(classification: ClassificationResult) -> str:
    """Short hint injected into the router when auto-delegate is not forced."""
    delegate = should_auto_delegate(classification)
    return (
        f"task_type={classification.task_type}, "
        f"complexity={classification.complexity}, "
        f"capabilities={classification.capabilities_required}, "
        f"suggested_provider={classification.suggested_provider}, "
        f"auto_delegate={'yes' if delegate else 'no'}"
    )
