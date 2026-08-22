from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from dispatch.provider_config import AccountSpec, ProviderSpec

LOGGER = logging.getLogger(__name__)

DEFAULT_COOLDOWN_SECONDS = 60.0
EXHAUSTED_COOLDOWN_SECONDS = 300.0


@dataclass(slots=True)
class ResolvedAccount:
    provider_id: str
    provider_name: str
    label: str
    api_key: str
    env_key: str


@dataclass(slots=True)
class AccountStatus:
    label: str
    provider_id: str
    available: bool
    on_cooldown: bool
    total_tokens: int
    requests: int
    remaining_requests: str | None
    remaining_tokens: str | None


def default_state_path() -> Path:
    return Path(__file__).resolve().parent / "state" / "usage_state.json"


def _parse_remaining(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class KeyPool:
    """
    Tracks per-account usage and picks the healthiest key next.
    Switches accounts automatically on 429, exhaustion, or low remaining quota.
    """

    def __init__(self, state_path: Path | None = None) -> None:
        self._state_path = state_path or default_state_path()
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return {"accounts": {}, "last_global_pick": None}
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOGGER.warning("Corrupt usage state at %s; resetting", self._state_path)
            return {"accounts": {}, "last_global_pick": None}
        data.setdefault("accounts", {})
        data.setdefault("last_global_pick", None)
        return data

    def _save_state(self) -> None:
        self._state_path.write_text(
            json.dumps(self._state, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _account_state(self, label: str) -> dict[str, Any]:
        accounts = self._state.setdefault("accounts", {})
        if label not in accounts:
            accounts[label] = {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "requests": 0,
                "cooldown_until": None,
                "last_used": None,
                "last_remaining_requests": None,
                "last_remaining_tokens": None,
                "exhausted_count": 0,
            }
        return accounts[label]

    def is_on_cooldown(self, label: str) -> bool:
        entry = self._account_state(label)
        cooldown_until = entry.get("cooldown_until")
        if cooldown_until is None:
            return False
        if time.time() >= float(cooldown_until):
            entry["cooldown_until"] = None
            self._save_state()
            return False
        return True

    def mark_cooldown(self, label: str, seconds: float = DEFAULT_COOLDOWN_SECONDS) -> None:
        entry = self._account_state(label)
        entry["cooldown_until"] = time.time() + seconds
        LOGGER.info("Account %s on cooldown for %.0fs", label, seconds)
        self._save_state()

    def mark_exhausted(self, label: str) -> None:
        entry = self._account_state(label)
        entry["exhausted_count"] = int(entry.get("exhausted_count", 0)) + 1
        self.mark_cooldown(label, EXHAUSTED_COOLDOWN_SECONDS)
        LOGGER.warning("Account %s marked exhausted — switching to next key", label)

    def _account_score(self, label: str) -> float:
        """Lower score = healthier account, picked first."""
        entry = self._account_state(label)
        score = float(entry.get("requests", 0))

        total_tokens = int(entry.get("total_input_tokens", 0)) + int(entry.get("total_output_tokens", 0))
        score += total_tokens / 10_000.0

        rem_req = _parse_remaining(entry.get("last_remaining_requests"))
        rem_tok = _parse_remaining(entry.get("last_remaining_tokens"))
        if rem_req is not None:
            score += max(0.0, 100.0 - rem_req)
        if rem_tok is not None:
            score += max(0.0, 100.0 - rem_tok) / 10.0

        score += int(entry.get("exhausted_count", 0)) * 50.0

        last_used = entry.get("last_used")
        if last_used is not None:
            score -= min(5.0, (time.time() - float(last_used)) / 60.0)

        return score

    def record_usage(
        self,
        label: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        headers: dict[str, str] | None = None,
    ) -> None:
        entry = self._account_state(label)
        entry["total_input_tokens"] = int(entry.get("total_input_tokens", 0)) + input_tokens
        entry["total_output_tokens"] = int(entry.get("total_output_tokens", 0)) + output_tokens
        entry["requests"] = int(entry.get("requests", 0)) + 1
        entry["last_used"] = time.time()

        if headers:
            for header_key, state_key in (
                ("x-ratelimit-remaining-requests", "last_remaining_requests"),
                ("x-ratelimit-remaining-tokens", "last_remaining_tokens"),
                ("anthropic-ratelimit-requests-remaining", "last_remaining_requests"),
                ("anthropic-ratelimit-tokens-remaining", "last_remaining_tokens"),
            ):
                if header_key in headers:
                    entry[state_key] = headers[header_key]

        self._save_state()

    def touch_account(self, label: str) -> None:
        entry = self._account_state(label)
        entry["last_used"] = time.time()
        self._save_state()

    def resolve_account(self, provider: ProviderSpec, account: AccountSpec) -> ResolvedAccount | None:
        api_key = os.environ.get(account.env_key, "").strip()
        if not api_key or self.is_on_cooldown(account.label):
            return None
        return ResolvedAccount(
            provider_id=provider.id,
            provider_name=provider.name,
            label=account.label,
            api_key=api_key,
            env_key=account.env_key,
        )

    def pick_accounts_ordered(self, provider: ProviderSpec) -> list[ResolvedAccount]:
        """Return accounts in catalog order (priority list controls routing, not this)."""
        resolved: list[ResolvedAccount] = []
        for account in provider.accounts:
            item = self.resolve_account(provider, account)
            if item:
                resolved.append(item)
        return resolved

    def pick_account(self, provider: ProviderSpec) -> ResolvedAccount | None:
        accounts = self.pick_accounts_ordered(provider)
        return accounts[0] if accounts else None

    def iter_api_accounts(
        self,
        providers: list[ProviderSpec],
        *,
        preferred_provider_id: str | None = None,
    ) -> Iterator[ResolvedAccount]:
        """
        Yield all available API accounts across providers in best order.
        Preferred provider's accounts first, then others by provider priority.
        """
        api_providers = [p for p in providers if p.kind == "api"]
        ordered = sorted(api_providers, key=lambda p: p.priority)

        if preferred_provider_id:
            preferred = next((p for p in ordered if p.id == preferred_provider_id), None)
            if preferred:
                ordered = [preferred] + [p for p in ordered if p.id != preferred_provider_id]

        seen: set[str] = set()
        for provider in ordered:
            for account in self.pick_accounts_ordered(provider):
                if account.label in seen:
                    continue
                seen.add(account.label)
                yield account

    def pool_status(self, providers: list[ProviderSpec]) -> list[AccountStatus]:
        rows: list[AccountStatus] = []
        for provider in providers:
            if provider.kind != "api":
                continue
            for account in provider.accounts:
                if not os.environ.get(account.env_key, "").strip():
                    continue
                entry = self._account_state(account.label)
                on_cd = self.is_on_cooldown(account.label)
                rows.append(
                    AccountStatus(
                        label=account.label,
                        provider_id=provider.id,
                        available=not on_cd,
                        on_cooldown=on_cd,
                        total_tokens=int(entry.get("total_input_tokens", 0))
                        + int(entry.get("total_output_tokens", 0)),
                        requests=int(entry.get("requests", 0)),
                        remaining_requests=entry.get("last_remaining_requests"),
                        remaining_tokens=entry.get("last_remaining_tokens"),
                    )
                )
        return rows
