from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from dispatch.key_pool import KeyPool, ResolvedAccount
from dispatch.provider_config import ProviderSpec, load_providers, provider_by_id, repo_root

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PriorityEntry:
    provider_id: str
    account_label: str

    @classmethod
    def parse(cls, raw: str) -> PriorityEntry | None:
        raw = raw.strip()
        if "/" not in raw:
            return None
        provider_id, account_label = raw.split("/", 1)
        provider_id = provider_id.strip()
        account_label = account_label.strip()
        if not provider_id or not account_label:
            return None
        return cls(provider_id=provider_id, account_label=account_label)


def default_priorities_path() -> Path:
    return repo_root() / "config" / "task_priorities.json"


def load_task_priorities(path: Path | None = None) -> dict[str, list[str]]:
    config_path = path or default_priorities_path()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    priorities = raw.get("priorities", {})
    return {task_type: list(entries) for task_type, entries in priorities.items()}


def load_app_handoff_priorities(path: Path | None = None) -> dict[str, list[str]]:
    config_path = path or default_priorities_path()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    handoff = raw.get("app_handoff", {})
    return {task_type: list(entries) for task_type, entries in handoff.items()}


class PriorityRouter:
    """
    Routes requests using your task-based priority lists — not quota heuristics.
    Walks the list top-to-bottom; only moves on when a call actually fails.
    """

    def __init__(
        self,
        providers: list[ProviderSpec] | None = None,
        key_pool: KeyPool | None = None,
        priorities_path: Path | None = None,
    ) -> None:
        self._providers = providers or load_providers()
        self._provider_map = {p.id: p for p in self._providers}
        self._key_pool = key_pool or KeyPool()
        self._priorities_path = priorities_path or default_priorities_path()
        self._priorities = load_task_priorities(self._priorities_path)
        self._app_handoff = load_app_handoff_priorities(self._priorities_path)

    def reload(self) -> None:
        self._priorities = load_task_priorities(self._priorities_path)
        self._app_handoff = load_app_handoff_priorities(self._priorities_path)

    def priority_list_for(self, task_type: str) -> list[str]:
        return self._priorities.get(task_type) or self._priorities.get("default", [])

    def app_handoff_list_for(self, task_type: str) -> list[str]:
        return self._app_handoff.get(task_type) or self._app_handoff.get("default", [])

    def resolve_api_chain(self, task_type: str) -> list[ResolvedAccount]:
        """Return API accounts in your priority order for this task type."""
        chain: list[ResolvedAccount] = []
        seen: set[str] = set()

        for entry_raw in self.priority_list_for(task_type):
            entry = PriorityEntry.parse(entry_raw)
            if not entry:
                LOGGER.warning("Invalid priority entry: %r", entry_raw)
                continue

            dedupe_key = f"{entry.provider_id}/{entry.account_label}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            provider = self._provider_map.get(entry.provider_id)
            if not provider or provider.kind != "api":
                continue

            account_spec = next(
                (a for a in provider.accounts if a.label == entry.account_label),
                None,
            )
            if not account_spec:
                continue

            resolved = self._key_pool.resolve_account(provider, account_spec)
            if resolved:
                chain.append(resolved)

        return chain

    def resolve_app_chain(self, task_type: str) -> list[ProviderSpec]:
        chain: list[ProviderSpec] = []
        seen: set[str] = set()

        for provider_id in self.app_handoff_list_for(task_type):
            if provider_id in seen:
                continue
            seen.add(provider_id)

            provider = provider_by_id(self._providers, provider_id)
            if provider and provider.kind == "app_session":
                chain.append(provider)

        return chain

    def describe_chain(self, task_type: str) -> list[str]:
        lines: list[str] = []
        for i, account in enumerate(self.resolve_api_chain(task_type), 1):
            lines.append(f"{i}. {account.provider_id}/{account.label}")
        if not lines:
            lines.append("(no API accounts configured for this priority list)")
        return lines
