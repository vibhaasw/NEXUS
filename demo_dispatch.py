#!/usr/bin/env python3
"""Walk through the dispatch pipeline step by step."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "voice_mod"))

from load_env import load_dotenv


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def main() -> int:
    load_dotenv()

    from dispatch.classifier import TaskClassifier
    from dispatch.key_pool import KeyPool
    from dispatch.orchestrator import AIOrchestrator
    from dispatch.provider_config import load_providers
    from voice_control.config import load_config
    from voice_control.llm import create_ollama_client, healthcheck

    config = load_config()
    client = create_ollama_client(config)

    section("1. Setup")
    print(f"Ollama model : {config.ollama_model}")
    try:
        healthcheck(client, config.ollama_model)
        print("Ollama       : reachable")
    except RuntimeError as exc:
        print(f"Ollama       : FAILED — {exc}")
        return 1

    providers = load_providers()
    print(f"Providers    : {len(providers)} in catalog")
    for p in providers:
        kind = p.kind
        if p.kind == "api":
            keys = sum(1 for a in p.accounts if os.environ.get(a.env_key, "").strip())
            print(f"  - {p.id:12} ({kind}) — {keys}/{len(p.accounts)} API keys loaded")
        else:
            print(f"  - {p.id:12} ({kind}) — handoff via clipboard + open app")

    section("2. Auto-routing decision (no 'use external AI' needed)")
    request = "uh so like can you explain how Rust ownership works, keep it simple"
    print(f"Voice input  : {request!r}")
    print("Classifying...")

    classifier = TaskClassifier(client, config.ollama_model)
    tags = classifier.classify(request)

    from dispatch.routing_policy import looks_like_local_action, should_auto_delegate

    auto = should_auto_delegate(tags) and not looks_like_local_action(request)
    print(f"task_type    : {tags.task_type}")
    print(f"complexity   : {tags.complexity}")
    print(f"capabilities : {tags.capabilities_required}")
    print(f"suggested    : {tags.suggested_provider}")
    print(f"simplified   : {tags.simplified_prompt!r}")
    print(f"auto-delegate: {auto}  ← router sends to external AI when True")
    print("\n→ You just speak normally. The local model decides if external AI is needed.")

    section("3. Account pool status (token management)")
    orchestrator = AIOrchestrator(client, config.ollama_model)
    summary = orchestrator.account_summary()
    if summary:
        for line in summary:
            print(f"  {line}")
    else:
        print("  No API keys loaded — add them to .env")
    print("\n→ Algo picks the healthiest account, switches on 429/exhaustion.")

    section("4. Account rotation order for this task")
    pool = KeyPool()
    api_accounts = list(
        pool.iter_api_accounts(
            orchestrator._api_providers_for(tags),
            preferred_provider_id=tags.suggested_provider,
        )
    )
    if api_accounts:
        print("API accounts will be tried in this order:")
        for i, acct in enumerate(api_accounts, 1):
            print(f"  {i}. {acct.provider_id} / {acct.label}")
    else:
        print("  No API accounts available — will use handoff or local fallback.")

    section("5. API dispatch attempt")
    has_any_key = any(
        os.environ.get(a.env_key, "").strip()
        for p in providers
        if p.kind == "api"
        for a in p.accounts
    )
    if not has_any_key:
        print("No API keys found in .env / .env.example.")
        print("Copy .env.example → .env and fill OPENAI_API_KEY_1, GEMINI_API_KEY_1, etc.")
        print("Skipping live API call.")
    else:
        print("Calling external API with simplified prompt...")
        result = orchestrator.dispatch(request)
        print(f"success      : {result.success}")
        print(f"provider     : {result.provider_id}")
        print(f"model        : {result.model}")
        print(f"account      : {result.account_label}")
        print(f"switched     : {result.switched_accounts} account(s)")
        print(f"handoff      : {result.handoff}")
        print(f"local        : {result.local_fallback}")
        print(f"attempts     : {result.attempts}")
        print(f"\nResponse:\n{result.output[:800]}{'...' if len(result.output) > 800 else ''}")

    section("6. App-session handoff demo (last resort before local fallback)")
    code_request = "refactor the login module to use async await"
    print(f"Request      : {code_request!r}")

    from dispatch.classifier import ClassificationResult

    code_tags = ClassificationResult(
        task_type="code",
        complexity="medium",
        capabilities_required=["code"],
        simplified_prompt="Refactor the login module to use async/await.",
        suggested_provider="cursor",
    )
    cursor = next((p for p in providers if p.id == "cursor"), None)
    if cursor:
        handoff = orchestrator._handoff_to_app(cursor, code_tags.simplified_prompt)
        print(f"success      : {handoff.success}")
        print(f"output       : {handoff.output}")
    else:
        print("Cursor not configured.")

    section("7. How this connects to voice")
    print("""
Full voice flow — always-on AI via account rotation:
  1. You speak normally (no 'use external AI')
  2. Local classifier picks task type + best provider
  3. Key pool selects healthiest account (most quota left)
  4. On 429/exhaustion → auto-switch to next account (OpenAI #2, Gemini #1, …)
  5. All API accounts busy → app handoff (Cursor/Claude) → local Ollama last resort

Run:
  cd /home/vibhaasw/unamed
  PYTHONPATH="$PWD:$PWD/voice_mod" python main.py
""")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
