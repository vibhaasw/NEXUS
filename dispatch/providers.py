from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger(__name__)


class RateLimitError(Exception):
    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderError(Exception):
    pass


@dataclass(slots=True)
class CompletionResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    headers: dict[str, str] | None = None
    model: str | None = None
    provider_id: str | None = None


def _normalize_headers(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if hasattr(raw, "items"):
        return {str(k).lower(): str(v) for k, v in raw.items()}
    return {}


def _http_post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    *,
    timeout: float = 120.0,
) -> tuple[dict[str, Any], dict[str, str]]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_headers = _normalize_headers(response.headers)
            data = json.loads(response.read().decode("utf-8"))
            return data, response_headers
    except urllib.error.HTTPError as exc:
        response_headers = _normalize_headers(exc.headers)
        detail = exc.read().decode("utf-8", errors="replace")
        detail_lower = detail.lower()
        quota_exhausted = (
            "insufficient_quota" in detail_lower
            or "exceeded your current quota" in detail_lower
            or "resource_exhausted" in detail_lower
        )
        if exc.code == 429 or quota_exhausted:
            retry_after = response_headers.get("retry-after")
            if retry_after:
                retry_seconds = float(retry_after)
            elif quota_exhausted:
                retry_seconds = 3600.0
            else:
                retry_seconds = 60.0
            raise RateLimitError(detail or "Rate limited", retry_after=retry_seconds) from exc
        raise ProviderError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"Network error: {exc}") from exc


class OpenAICompatibleProvider:
    def __init__(self, provider_id: str, base_url: str) -> None:
        self.provider_id = provider_id
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, model: str, api_key: str) -> CompletionResult:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        data, response_headers = _http_post_json(url, payload, headers)
        choices = data.get("choices") or []
        message = choices[0].get("message", {}) if choices else {}
        text = message.get("content", "") or ""
        usage = data.get("usage") or {}
        return CompletionResult(
            text=text.strip(),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            headers=response_headers,
            model=model,
            provider_id=self.provider_id,
        )


class AnthropicProvider:
    def __init__(self, provider_id: str, base_url: str) -> None:
        self.provider_id = provider_id
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, model: str, api_key: str) -> CompletionResult:
        url = f"{self.base_url}/v1/messages"
        payload = {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        data, response_headers = _http_post_json(url, payload, headers)
        content_blocks = data.get("content") or []
        text_parts = [
            block.get("text", "")
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        usage = data.get("usage") or {}
        return CompletionResult(
            text="\n".join(text_parts).strip(),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            headers=response_headers,
            model=model,
            provider_id=self.provider_id,
        )


class GeminiProvider:
    def __init__(self, provider_id: str, base_url: str) -> None:
        self.provider_id = provider_id
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, model: str, api_key: str) -> CompletionResult:
        url = f"{self.base_url}/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
        }
        headers = {"Content-Type": "application/json"}
        data, response_headers = _http_post_json(url, payload, headers)
        candidates = data.get("candidates") or []
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "\n".join(part.get("text", "") for part in parts if isinstance(part, dict))
        usage = data.get("usageMetadata") or {}
        return CompletionResult(
            text=text.strip(),
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
            headers=response_headers,
            model=model,
            provider_id=self.provider_id,
        )


def build_adapter(provider_id: str, adapter: str, base_url: str) -> OpenAICompatibleProvider | AnthropicProvider | GeminiProvider:
    if adapter == "anthropic":
        return AnthropicProvider(provider_id, base_url)
    if adapter == "gemini":
        return GeminiProvider(provider_id, base_url)
    return OpenAICompatibleProvider(provider_id, base_url)
