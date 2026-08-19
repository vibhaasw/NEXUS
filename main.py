"""Top-level entry point for Voice Mod."""
from __future__ import annotations

import sys

from voice_control.audio import AudioController
from voice_control.config import load_config
from voice_control.llm import create_ollama_client, healthcheck
from voice_control.router import IntentRouter
from voice_control.stt import RealtimeSpeechToText
from voice_control.utils import configure_logging
from handlers import (
    CodeHandler,
    EditFileHandler,
    HandlerRegistry,
    OpenAppHandler,
    QAHandler,
    WebSearchHandler,
)


def _build_registry(client, model: str) -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register(QAHandler(client, model))
    registry.register(CodeHandler())
    registry.register(WebSearchHandler())
    registry.register(OpenAppHandler())
    registry.register(EditFileHandler())
    return registry


def main() -> int:
    config = load_config()
    configure_logging(config.debug)

    client = create_ollama_client(config)
    healthcheck(client, config.ollama_model)

    audio = AudioController()
    stt = RealtimeSpeechToText(config)
    registry = _build_registry(client, config.ollama_model)
    router = IntentRouter(client, config.ollama_model, registry)

    print("Voice Mod ready.")
    print(f"Ollama model: {config.ollama_model}")
    print(f"Handlers: {', '.join(registry.handler_names())}")
    print("Press Enter to start recording, Enter again to stop, or type 'q' to quit.")

    try:
        while True:
            command = input("\nReady> ").strip().lower()
            if command in {"q", "quit", "exit"}:
                print("Exiting.")
                return 0

            print("Listening... press Enter to stop.")
            stt.start_recording()
            audio.mark_started()
            input()
            stt.stop_recording()
            audio.mark_stopped()

            transcript = stt.transcribe_current_recording()
            if not transcript.accepted:
                print(f"Transcript ignored: {transcript.reason}")
                continue

            print(f"\nTranscript: {transcript.text}")
            print("Routing...")

            routed = router.route(transcript.text)

            status = "OK" if routed.success else "FAILED"
            print(f"[{routed.handler_name}] ({status})")
            print(f"  {routed.reply}")

            if routed.raw_args:
                print(f"  Args: {routed.raw_args}")

    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        return 1
    finally:
        stt.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
