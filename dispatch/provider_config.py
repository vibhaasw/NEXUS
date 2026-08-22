from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ProviderKind = Literal["api", "app_session"]
AdapterKind = Literal["openai_compatible", "anthropic", "gemini"]


@dataclass(slots=True)
class AccountSpec:
    env_key: str
    label: str


@dataclass(slots=True)
class ProviderSpec:
    id: str
    name: str
    kind: ProviderKind
    capabilities: list[str]
    priority: int = 100
    adapter: AdapterKind | None = None
    base_url: str | None = None
    models: dict[str, str] = field(default_factory=dict)
    accounts: list[AccountSpec] = field(default_factory=list)
    launch_target: str | None = None

    def model_for_task(self, task_type: str) -> str | None:
        return self.models.get(task_type) or self.models.get("reasoning")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_providers_path() -> Path:
    return repo_root() / "config" / "providers.json"


def load_providers(path: Path | None = None) -> list[ProviderSpec]:
    config_path = path or default_providers_path()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    providers: list[ProviderSpec] = []

    for entry in raw.get("providers", []):
        accounts = [
            AccountSpec(env_key=a["env_key"], label=a["label"])
            for a in entry.get("accounts", [])
        ]
        providers.append(
            ProviderSpec(
                id=entry["id"],
                name=entry["name"],
                kind=entry.get("kind", "api"),
                capabilities=list(entry.get("capabilities", [])),
                priority=int(entry.get("priority", 100)),
                adapter=entry.get("adapter"),
                base_url=entry.get("base_url"),
                models=dict(entry.get("models", {})),
                accounts=accounts,
                launch_target=entry.get("launch_target"),
            )
        )

    providers.sort(key=lambda p: p.priority)
    return providers


def provider_by_id(providers: list[ProviderSpec], provider_id: str) -> ProviderSpec | None:
    for provider in providers:
        if provider.id == provider_id:
            return provider
    return None
