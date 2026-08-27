# NEXUS

**A local-first voice assistant that classifies its own tasks and decides — on its own — when to answer locally, hand off to an external AI, or run an action on your machine.**

> ⚠️ **Under active development.** Interfaces, config formats, and provider support are still changing. Not production-ready.

---

## What NEXUS actually does right now

You talk to it. A local Ollama model listens to the transcript, tags what kind of task it is, and decides what happens to it — without you ever saying "use GPT" or "search for this":

- **Simple questions and small talk** get answered immediately by the local model. No network call, no cost.
- **Machine actions** — "open Firefox," "search the web for X," "edit config.py" — get routed straight to a handler that executes them.
- **Complex reasoning, heavier code, vision, or long-context tasks** get automatically delegated to an external AI provider, chosen by your own priority list and account rotation — the user never has to ask for it.
- **If every configured API account fails**, it falls back to handing the task off to a local app (Cursor, Claude desktop, Copilot) via clipboard + launch, and if that's not available either, it falls back to the local Ollama model one last time so a request never just dies with no answer.

Nothing here is a chatbot wrapper — it's a routing brain in front of a set of independent handlers.

---

## Architecture

```
Voice input (mic)
      │
      ▼
Speech-to-text (RealtimeSTT)
      │
      ▼
Local task classifier (Ollama)  ──►  task_type, complexity, capabilities_required,
      │                              simplified_prompt, suggested_provider
      ▼
IntentRouter
      │
      ├── fast-path regex match ──► handler executes directly (open app / search / edit)
      │
      └── tool-calling to local model ──► HandlerRegistry
                                                │
                     ┌──────────────────────────┼───────────────────────────┐
                     ▼                          ▼                           ▼
              QAHandler                  CodeHandler /                DelegateAIHandler
           (local Q&A, no             WebSearchHandler /                    │
            external call)            OpenAppHandler /                     ▼
                                       EditFileHandler              AIOrchestrator
                                     (local machine actions)               │
                                                              ┌────────────┼────────────┐
                                                              ▼            ▼            ▼
                                                       Priority chain  App handoff  Local Ollama
                                                       (your ordered  (clipboard +   fallback
                                                        API accounts)  open_app)   (last resort)
```

The local model is the only thing that ever decides where a request goes. External AI is a tool it reaches for, not a default.

---

## Repository layout

```
NEXUS/
├── main.py                      Entry point: wires config, registry, and the router together
├── demo_dispatch.py             Standalone script to walk the dispatch pipeline step by step
├── load_env.py                  Minimal stdlib .env loader (no external dependency)
│
├── voice_mod/                   Voice capture + local intent routing
│   └── voice_control/
│       ├── audio.py             Mic recording controller
│       ├── stt.py               RealtimeSTT wrapper, transcript acceptance rules
│       ├── llm.py                Ollama client creation + healthcheck
│       ├── router.py            IntentRouter — fast-path regex + tool-calling dispatch
│       ├── prompts.py           Router system prompt
│       └── config.py            Env-var driven configuration
│
├── handlers/                    Independent, tool-callable actions
│   ├── base.py                  BaseHandler / HandlerResult / HandlerRegistry
│   ├── qa_handler.py            Local Q&A via Ollama, no external call
│   ├── code_handler.py          Delegates to a local coding CLI (opencode / claude)
│   ├── web_search_handler.py    Opens a web search in the default browser
│   ├── open_app_handler.py      Opens apps, URLs, or a URL inside a specific browser
│   ├── edit_file_handler.py     Opens a file in the user's preferred editor
│   └── delegate_ai_handler.py   Bridges the router to the dispatch/AIOrchestrator
│
├── dispatch/                    Local-AI-governed multi-provider task dispatch
│   ├── classifier.py            TaskClassifier — turns a transcript into a structured task
│   ├── routing_policy.py        should_auto_delegate() — decides local vs. external
│   ├── priority_router.py       Reads config/task_priorities.json, resolves ordered chains
│   ├── provider_config.py       Loads config/providers.json into typed ProviderSpec objects
│   ├── providers.py             REST adapters: OpenAI-compatible / Anthropic / Gemini
│   ├── key_pool.py              Per-account usage tracking, cooldowns, account health scoring
│   ├── orchestrator.py          Ties it all together: classify → priority chain → app handoff → local fallback
│   ├── prompts.py               Task classifier system prompt
│   └── state/                   Runtime-generated usage state (gitignored)
│
├── config/
│   ├── providers.json           Provider capability catalog — env var *names* only, never keys
│   └── task_priorities.json     Your own ordered provider/account list, per task type
│
├── tests/
│   ├── test_dispatch.py         Classifier parsing, orchestrator fallback behavior
│   └── test_routing_policy.py   Local-action regex matching, auto-delegate rules
│
├── .env.example                 Documents every expected env var — copy to .env and fill in
└── .gitignore                   Keeps .env, usage_state.json, caches, and logs out of git
```

---

## Setup

```bash
git clone https://github.com/vibhaasw/NEXUS.git
cd NEXUS
python -m venv .venv
source .venv/bin/activate
pip install -r voice_mod/requirements.txt

cp .env.example .env
# then edit .env and fill in your own API keys — see below
```

`.env` is gitignored. **Never commit it, and never paste real API keys into a chat, issue, or commit message** — treat any key that's been shared outside `.env` as compromised and rotate it immediately.

### Required local dependency

NEXUS needs [Ollama](https://ollama.com) running locally — this is the model that does all the classification and routing, and it's what keeps NEXUS working even with zero external API keys configured.

```bash
ollama serve
ollama pull phi4-mini:latest   # or your preferred model — see VOICE_MOD_OLLAMA_MODEL below
```

### Configuring external AI providers

Every provider in `config/providers.json` only references **environment variable names**, never actual secrets:

```bash
# .env
OPENAI_API_KEY_1=...
OPENAI_API_KEY_2=...
GEMINI_API_KEY_1=...
GEMINI_API_KEY_2=...
ANTHROPIC_API_KEY=...
```

You control routing yourself in `config/task_priorities.json` — it's a simple ordered list per task type (`"provider_id/account_label"`), walked top to bottom. Nothing is auto-scored or guessed; if you want Gemini tried before OpenAI for coding tasks, just reorder the list.

`app_session` providers (Cursor, Claude desktop, GitHub Copilot) don't need API keys at all — they have none on their free tiers, so NEXUS instead copies the simplified prompt to your clipboard and opens the app for you to paste it in. This is intentionally a handoff, not automation — full desktop control is a separate, later phase of this project.

---

## Running it

```bash
python main.py
```

Press Enter to start recording, Enter again to stop. NEXUS prints the transcript, which handler it routed to, whether it auto-delegated to an external AI, and (in debug mode) the full attempt trail — which providers and accounts were tried and why any of them failed.

To inspect the dispatch pipeline directly without the voice loop:

```bash
python demo_dispatch.py
```

---

## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `VOICE_MOD_OLLAMA_MODEL` | `phi4-mini:latest` | Local model used for classification and routing |
| `OLLAMA_HOST` | — | Custom Ollama host, if not running on default |
| `VOICE_MOD_LANGUAGE` | `en` | STT language |
| `VOICE_MOD_STT_MODEL` | `tiny` | faster-whisper model size |
| `VOICE_MOD_STT_ENGINE` | `faster_whisper` | STT backend |
| `VOICE_MOD_DEVICE` | `cpu` | STT compute device |
| `VOICE_MOD_INPUT_DEVICE_INDEX` | — | Specific mic device index |
| `VOICE_MOD_POST_SPEECH_SILENCE` | `0.6` | Silence duration that ends an utterance |
| `VOICE_MOD_DEBUG` | `false` | Verbose logging, including the dispatch attempt trail |
| `OPENAI_API_KEY_1`, `OPENAI_API_KEY_2`, `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, `ANTHROPIC_API_KEY`, ... | — | External provider keys — see `.env.example` for the full list |

---

## Testing

```bash
pytest tests/ -v
```

Covers classifier JSON parsing (including malformed-output fallback), the auto-delegate decision rules, and local-action regex matching.

---

## Status and what's next

Working today: voice capture → transcription → local classification → routing to local handlers or external AI, with priority-based account rotation and a three-tier fallback chain (external API → app handoff → local model).

Deliberately not built yet:
- Actual desktop/UI automation for `app_session` providers (typing into Cursor/Claude/Copilot for you) — planned as a separate phase, kept out of this dispatch layer on purpose.
- Broader provider coverage beyond the OpenAI-compatible / Anthropic / Gemini adapters already in place.
- Dual-boot / secure-boot tooling referenced in earlier project notes — not part of the current codebase.

Contributions and issues are welcome, but expect breaking changes while this is still taking shape.