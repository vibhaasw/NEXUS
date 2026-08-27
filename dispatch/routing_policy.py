from __future__ import annotations

import re

from dispatch.classifier import ClassificationResult

_OPEN_IN_BROWSER_RE = re.compile(
    r"\b(?:open|launch)\s+(.+?)\s+(?:in|with|using|via)\s+"
    r"([a-zA-Z0-9._+\-]+(?:\s+(?!for\b|me\b|please\b|now\b)[a-zA-Z0-9._+\-]+)?)",
    re.IGNORECASE,
)
_OPEN_RE = re.compile(
    r"\b(?:open|launch)\s+(.+?)(?:\s+(?:please|for me|now))?\s*$",
    re.IGNORECASE,
)
_SEARCH_RE = re.compile(
    r"\b(?:search the web for|search for|google|look up online)\s+(.+)",
    re.IGNORECASE,
)
_EDIT_RE = re.compile(r"\b(?:edit|modify|open file)\s+(.+)", re.IGNORECASE)

_APP_FILLER = re.compile(
    r"\b(the|a|an|my|app|application|please|for me|on my (?:computer|desktop)|now)\b",
    re.IGNORECASE,
)


def _clean_app_target(raw: str) -> str:
    text = raw.strip(" .,\"'!?")
    text = _APP_FILLER.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def looks_like_local_action(transcript: str) -> bool:
    """True when the user is clearly asking to act on the machine, not ask an AI."""
    lower = transcript.lower()
    return bool(
        _OPEN_IN_BROWSER_RE.search(transcript)
        or _OPEN_RE.search(transcript)
        or _SEARCH_RE.search(transcript)
        or _EDIT_RE.search(transcript)
        or re.search(r"\b(search the web|google|look up online)\b", lower)
        or re.search(
            r"\b(?:open|launch)\b.+\b(?:app|application|spotify|firefox|chrome|terminal)\b",
            lower,
        )
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

    # Generic: open <site|url> in|with <browser>
    if m := _OPEN_IN_BROWSER_RE.search(transcript):
        what = _clean_app_target(m.group(1))
        browser = _clean_app_target(m.group(2))
        if what and browser:
            return "open_app", {"app": browser, "url": what, "target": f"{what} in {browser}"}

    if m := _OPEN_RE.search(transcript):
        target = _clean_app_target(m.group(1))
        if target:
            return "open_app", {"target": target}

    return None


def should_auto_delegate(classification: ClassificationResult) -> bool:
    """
    Local classifier decides when a task needs an external AI.

    Local Ollama / handlers keep:
      - fast_lookup, low complexity, medium reasoning/creative chat

    External AI (Gemini/OpenAI/…) gets:
      - high complexity
      - vision
      - medium+ code (heavier coding than local Q&A)
    """
    if classification.task_type == "fast_lookup":
        return False

    if classification.complexity == "low":
        return False

    if classification.complexity == "high":
        return True

    if classification.task_type == "vision":
        return True

    if classification.task_type == "code" and classification.complexity == "medium":
        return True

    return False


def prefers_local_answer(classification: ClassificationResult) -> bool:
    """True when local Ollama should answer without calling cloud APIs."""
    return not should_auto_delegate(classification)


def routing_hint(classification: ClassificationResult) -> str:
    """Short hint injected into the local tool-calling router."""
    delegate = should_auto_delegate(classification)
    return (
        f"task_type={classification.task_type}, "
        f"complexity={classification.complexity}, "
        f"capabilities={classification.capabilities_required}, "
        f"suggested_provider={classification.suggested_provider}, "
        f"auto_delegate={'yes' if delegate else 'no'}, "
        f"prefer_local={'yes' if not delegate else 'no'}"
    )
