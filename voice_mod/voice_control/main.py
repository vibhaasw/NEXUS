from __future__ import annotations

import sys

from voice_control.audio import AudioController
from voice_control.config import load_config
from voice_control.llm import OllamaRouterClient
from voice_control.router import IntentRouter
from voice_control.stt import RealtimeSpeechToText
from voice_control.utils import compact_json, configure_logging


def main() -> int:
    config = load_config()
    configure_logging(config.debug)

    audio = AudioController()
    stt = RealtimeSpeechToText(config)
    llm_client = OllamaRouterClient(config)
    llm_client.healthcheck()
    router = IntentRouter(llm_client)

    print("Voice Mod ready.")
    print(f"Ollama model: {llm_client.model_name}")
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

            print(f"Transcript: {transcript.text}")
            routed = router.route(transcript.text)
            print(f"Mode: {routed.mode}")
            print(f"Reply: {routed.reply}")
            if routed.mode == "command":
                print(f"Structured action: {compact_json(routed.command_args)}")
                if routed.command_name:
                    print(f"Command name: {routed.command_name}")
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as exc:  # pragma: no cover - top-level defensive handling
        print(f"Fatal error: {exc}", file=sys.stderr)
        return 1
    finally:
        stt.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
