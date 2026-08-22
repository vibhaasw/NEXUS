from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ollama import Client, ResponseError

from dispatch.classifier import ClassificationResult, TaskClassifier
from dispatch.key_pool import KeyPool
from dispatch.priority_router import PriorityRouter
from dispatch.provider_config import load_providers
from dispatch.providers import RateLimitError, build_adapter

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DispatchResult:
    success: bool
    output: str
    provider_id: str | None = None
    model: str | None = None
    account_label: str | None = None
    classification: ClassificationResult | None = None
    handoff: bool = False
    local_fallback: bool = False
    switched_accounts: int = 0
    attempts: list[str] = field(default_factory=list)


class AIOrchestrator:
    """
    Classifies the request, then walks your task-based priority list.
    Only tries the next entry when the current one fails — no quota-watching logic.
    """

    def __init__(
        self,
        client: Client,
        model: str,
        *,
        providers_path: Path | None = None,
        priorities_path: Path | None = None,
        key_pool: KeyPool | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._classifier = TaskClassifier(client, model)
        self._providers = load_providers(providers_path)
        self._key_pool = key_pool or KeyPool()
        self._priority_router = PriorityRouter(
            self._providers,
            self._key_pool,
            priorities_path=priorities_path,
        )
        self._provider_map = {p.id: p for p in self._providers}

    def dispatch(self, request: str) -> DispatchResult:
        classification = self._classifier.classify(request)
        prompt = classification.simplified_prompt
        attempts: list[str] = []

        api_result = self._try_priority_chain(classification, prompt, attempts)
        if api_result:
            api_result.classification = classification
            api_result.switched_accounts = len([a for a in attempts if a.startswith(("429:", "error:"))])
            return api_result

        handoff = self._try_app_handoff(classification, prompt, attempts)
        if handoff:
            handoff.classification = classification
            handoff.switched_accounts = len([a for a in attempts if a.startswith(("429:", "error:"))])
            return handoff

        local = self._try_local_fallback(prompt, attempts)
        local.classification = classification
        return local

    def _try_priority_chain(
        self,
        classification: ClassificationResult,
        prompt: str,
        attempts: list[str],
    ) -> DispatchResult | None:
        chain = self._priority_router.resolve_api_chain(classification.task_type)
        if not chain:
            attempts.append(f"skip:no-priority-chain:{classification.task_type}")
            return None

        attempts.append(f"priority:{classification.task_type}:" + "→".join(
            f"{a.provider_id}/{a.label}" for a in chain
        ))

        for account in chain:
            provider = self._provider_map.get(account.provider_id)
            if not provider:
                continue

            model = provider.model_for_task(classification.task_type)
            if not model:
                attempts.append(f"skip:{provider.id}:no-model")
                continue

            attempts.append(f"try:{provider.id}:{account.label}")
            LOGGER.info("Priority route: %s/%s for task %s", provider.id, account.label, classification.task_type)

            adapter = build_adapter(
                provider.id,
                provider.adapter or "openai_compatible",
                provider.base_url or "",
            )

            try:
                completion = adapter.complete(prompt, model, account.api_key)
                self._key_pool.record_usage(
                    account.label,
                    input_tokens=completion.input_tokens,
                    output_tokens=completion.output_tokens,
                    headers=completion.headers,
                )
                attempts.append(f"ok:{provider.id}:{account.label}")
                return DispatchResult(
                    success=True,
                    output=completion.text or "(empty response)",
                    provider_id=provider.id,
                    model=model,
                    account_label=account.label,
                    attempts=attempts,
                )
            except RateLimitError as exc:
                cooldown = exc.retry_after or 60.0
                self._key_pool.mark_cooldown(account.label, cooldown)
                attempts.append(f"429:{provider.id}:{account.label}")
                LOGGER.warning("Failed at %s/%s — trying next in priority list", provider.id, account.label)
            except Exception as exc:
                attempts.append(f"error:{provider.id}:{account.label}:{exc}")
                LOGGER.warning("Failed at %s/%s — trying next in priority list: %s", provider.id, account.label, exc)

        attempts.append("exhausted:priority-list")
        return None

    def _try_app_handoff(
        self,
        classification: ClassificationResult,
        prompt: str,
        attempts: list[str],
    ) -> DispatchResult | None:
        for provider in self._priority_router.resolve_app_chain(classification.task_type):
            attempts.append(f"handoff:{provider.id}")
            result = self._handoff_to_app(provider, prompt)
            if result.success:
                result.attempts = attempts
                return result
        return None

    def _try_local_fallback(self, prompt: str, attempts: list[str]) -> DispatchResult:
        attempts.append("fallback:local-ollama")
        LOGGER.info("Priority list exhausted — falling back to local Ollama")
        try:
            response = self._client.chat(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant. External priority providers failed. "
                        "Answer concisely from local knowledge.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.message.content if response.message else ""
            return DispatchResult(
                success=True,
                output=(content or "").strip() or "No local response generated.",
                provider_id="local-ollama",
                model=self._model,
                local_fallback=True,
                attempts=attempts,
            )
        except (ConnectionError, ResponseError) as exc:
            return DispatchResult(
                success=False,
                output=f"All priority providers failed and local fallback failed: {exc}",
                attempts=attempts,
            )

    def _handoff_to_app(self, provider, prompt: str) -> DispatchResult:
        target = provider.launch_target or provider.id
        copied = self._copy_to_clipboard(prompt)
        opened = self._open_target(target)

        if not copied and not opened:
            return DispatchResult(
                success=False,
                output=f"Could not hand off to {provider.name}.",
                provider_id=provider.id,
                handoff=True,
            )

        parts = [f"Handed off to {provider.name}."]
        if copied:
            parts.append("Prompt copied to clipboard.")
        if opened:
            parts.append(f"Opened {target}.")
        parts.append("Paste the prompt in the app to continue.")

        return DispatchResult(
            success=True,
            output=" ".join(parts),
            provider_id=provider.id,
            handoff=True,
        )

    @staticmethod
    def _copy_to_clipboard(text: str) -> bool:
        for cmd in (
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ):
            try:
                subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=5)
                return True
            except (FileNotFoundError, subprocess.SubprocessError):
                continue
        return False

    @staticmethod
    def _open_target(target: str) -> bool:
        for cmd in ([target], ["xdg-open", target]):
            try:
                subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True
            except (FileNotFoundError, OSError):
                continue
        return False

    def priority_chain_for(self, task_type: str) -> list[str]:
        return self._priority_router.describe_chain(task_type)

    def account_summary(self) -> list[str]:
        lines: list[str] = []
        for row in self._key_pool.pool_status(self._providers):
            status = "ready" if row.available else "cooldown"
            lines.append(f"{row.provider_id}/{row.label}: {status} | {row.requests} requests")
        return lines
