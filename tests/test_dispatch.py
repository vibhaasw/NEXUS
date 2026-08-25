import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dispatch.classifier import default_classification, parse_classification_payload
from dispatch.key_pool import KeyPool
from dispatch.orchestrator import AIOrchestrator
from dispatch.provider_config import load_providers
from dispatch.providers import OpenAICompatibleProvider, RateLimitError
from handlers.delegate_ai_handler import DelegateAIHandler


@pytest.fixture
def providers_path(tmp_path: Path) -> Path:
    catalog = {
        "providers": [
            {
                "id": "openai",
                "name": "OpenAI",
                "kind": "api",
                "adapter": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "priority": 10,
                "capabilities": ["reasoning", "code"],
                "models": {"reasoning": "test-model"},
                "accounts": [{"env_key": "TEST_OPENAI_KEY", "label": "test-openai"}],
            },
            {
                "id": "cursor",
                "name": "Cursor",
                "kind": "app_session",
                "priority": 80,
                "capabilities": ["code"],
                "launch_target": "cursor",
                "accounts": [],
            },
        ]
    }
    path = tmp_path / "providers.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    return path


def test_parse_classification_valid_json():
    payload = json.dumps(
        {
            "task_type": "code",
            "complexity": "high",
            "capabilities_required": ["code"],
            "simplified_prompt": "Write a Python fibonacci function.",
            "suggested_provider": "openai",
        }
    )
    result = parse_classification_payload(payload, "uh write fibonacci in python please")

    assert result.used_fallback is False
    assert result.task_type == "code"
    assert result.simplified_prompt == "Write a Python fibonacci function."
    assert result.suggested_provider == "openai"


def test_parse_classification_malformed_json_falls_back():
    result = parse_classification_payload("not json at all", "explain quantum computing")

    assert result.used_fallback is True
    assert result.task_type == "reasoning"
    assert result.complexity == "low"
    assert result.simplified_prompt == "explain quantum computing"
    assert result.suggested_provider is None


def test_key_pool_cooldown(tmp_path, monkeypatch):
    state_path = tmp_path / "usage_state.json"
    pool = KeyPool(state_path=state_path)

    from dispatch.provider_config import AccountSpec, ProviderSpec

    spec = ProviderSpec(
        id="openai",
        name="OpenAI",
        kind="api",
        capabilities=["reasoning"],
        accounts=[AccountSpec(env_key="TEST_KEY", label="test-label")],
    )
    monkeypatch.setenv("TEST_KEY", "secret")
    account = pool.pick_account(spec)
    assert account is not None

    pool.mark_cooldown("test-label", seconds=3600)
    assert pool.pick_account(spec) is None


def test_openai_provider_parses_response(monkeypatch):
    provider = OpenAICompatibleProvider("openai", "https://api.example.com/v1")

    class FakeResponse:
        headers = {"X-RateLimit-Remaining-Requests": "99"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": "Hello from API"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
            ).encode()

    monkeypatch.setattr("dispatch.providers.urllib.request.urlopen", lambda *a, **k: FakeResponse())
    result = provider.complete("hi", "test-model", "fake-key")

    assert result.text == "Hello from API"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.headers["x-ratelimit-remaining-requests"] == "99"


def test_orchestrator_api_dispatch(monkeypatch, providers_path, tmp_path):
    monkeypatch.setenv("TEST_OPENAI_KEY", "fake-key")

    priorities = {
        "priorities": {
            "default": ["openai/test-openai"],
            "reasoning": ["openai/test-openai"],
        },
        "app_handoff": {"default": ["cursor"]},
    }
    priorities_path = tmp_path / "task_priorities.json"
    priorities_path.write_text(json.dumps(priorities), encoding="utf-8")

    mock_client = MagicMock()
    orchestrator = AIOrchestrator(
        mock_client,
        "test-model",
        providers_path=providers_path,
        priorities_path=priorities_path,
        key_pool=KeyPool(state_path=tmp_path / "usage_state.json"),
    )

    classification = default_classification("Summarize Rust ownership.")
    classification.simplified_prompt = "Summarize Rust ownership."
    classification.task_type = "reasoning"
    monkeypatch.setattr(orchestrator, "_classifier", MagicMock(classify=lambda _: classification))

    fake_completion = MagicMock(
        text="Rust ownership summary.",
        input_tokens=1,
        output_tokens=2,
        headers={"x-ratelimit-remaining-tokens": "1000"},
    )
    monkeypatch.setattr(
        "dispatch.orchestrator.build_adapter",
        lambda *args: MagicMock(complete=lambda *a, **k: fake_completion),
    )

    result = orchestrator.dispatch("Summarize Rust ownership.")
    assert result.success is True
    assert "Rust ownership summary" in result.output
    assert result.provider_id == "openai"


def test_orchestrator_switches_account_on_429(monkeypatch, tmp_path):
    catalog = {
        "providers": [
            {
                "id": "openai",
                "name": "OpenAI",
                "kind": "api",
                "adapter": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "priority": 10,
                "capabilities": ["reasoning"],
                "models": {"reasoning": "test-model"},
                "accounts": [
                    {"env_key": "KEY_A", "label": "acct-a"},
                    {"env_key": "KEY_B", "label": "acct-b"},
                ],
            }
        ]
    }
    path = tmp_path / "providers.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    priorities = {
        "priorities": {
            "default": ["openai/acct-a", "openai/acct-b"],
            "reasoning": ["openai/acct-a", "openai/acct-b"],
        },
        "app_handoff": {"default": []},
    }
    priorities_path = tmp_path / "task_priorities.json"
    priorities_path.write_text(json.dumps(priorities), encoding="utf-8")
    monkeypatch.setenv("KEY_A", "a")
    monkeypatch.setenv("KEY_B", "b")

    orchestrator = AIOrchestrator(
        MagicMock(),
        "test-model",
        providers_path=path,
        priorities_path=priorities_path,
        key_pool=KeyPool(state_path=tmp_path / "usage_state.json"),
    )
    classification = default_classification("Explain async Rust.")
    classification.simplified_prompt = "Explain async Rust."
    classification.task_type = "reasoning"
    monkeypatch.setattr(orchestrator, "_classifier", MagicMock(classify=lambda _: classification))

    calls: list[str] = []

    class FlakyAdapter:
        def complete(self, prompt, model, api_key):
            calls.append(api_key)
            if api_key == "a":
                raise RateLimitError("429", retry_after=30)
            return MagicMock(
                text="Answer from second account.",
                input_tokens=1,
                output_tokens=1,
                headers={"x-ratelimit-remaining-tokens": "500"},
            )

    monkeypatch.setattr("dispatch.orchestrator.build_adapter", lambda *args: FlakyAdapter())

    result = orchestrator.dispatch("Explain async Rust.")
    assert result.success is True
    assert result.account_label == "acct-b"
    assert result.switched_accounts == 1
    assert calls == ["a", "b"]


def test_orchestrator_app_session_handoff(monkeypatch, providers_path, tmp_path):
    priorities = {
        "priorities": {"default": [], "reasoning": []},
        "app_handoff": {"default": ["cursor"], "code": ["cursor"]},
    }
    priorities_path = tmp_path / "task_priorities.json"
    priorities_path.write_text(json.dumps(priorities), encoding="utf-8")

    mock_client = MagicMock()
    orchestrator = AIOrchestrator(
        mock_client,
        "test-model",
        providers_path=providers_path,
        priorities_path=priorities_path,
        key_pool=KeyPool(state_path=tmp_path / "usage_state.json"),
    )

    classification = default_classification("Refactor this module")
    classification.simplified_prompt = "Refactor this module"
    classification.task_type = "code"
    classification.capabilities_required = ["code"]
    classification.suggested_provider = "cursor"
    monkeypatch.setattr(orchestrator, "_classifier", MagicMock(classify=lambda _: classification))

    monkeypatch.setattr(orchestrator, "_copy_to_clipboard", lambda text: True)
    monkeypatch.setattr(orchestrator, "_open_target", lambda target: True)

    result = orchestrator.dispatch("Refactor this module")
    assert result.success is True
    assert result.handoff is True
    assert result.provider_id == "cursor"


def test_delegate_handler_requires_request():
    handler = DelegateAIHandler(MagicMock(), "test-model")
    result = handler.execute(request="")
    assert result.success is False


def test_load_providers_catalog():
    providers = load_providers()
    assert len(providers) == 10
    ids = {p.id for p in providers}
    assert "openai" in ids
    assert "cursor" in ids
    assert "copilot" in ids
