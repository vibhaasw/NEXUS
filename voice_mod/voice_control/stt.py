from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from voice_control.config import AppConfig

LOGGER = logging.getLogger(__name__)

_FILLER_ONLY_RE = re.compile(r"^(?:\s|uh|um|hmm|mm+|erm|ah|like)+$", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class TranscriptResult:
    text: str
    raw_text: str
    accepted: bool
    reason: str | None = None


def normalize_transcript(text: str) -> TranscriptResult:
    raw_text = text or ""
    cleaned = _SPACE_RE.sub(" ", raw_text).strip()
    cleaned = cleaned.strip("., ")

    if not cleaned:
        return TranscriptResult(text="", raw_text=raw_text, accepted=False, reason="empty transcript")

    if _FILLER_ONLY_RE.fullmatch(cleaned):
        return TranscriptResult(text=cleaned, raw_text=raw_text, accepted=False, reason="filler-only transcript")

    return TranscriptResult(text=cleaned, raw_text=raw_text, accepted=True)


class RealtimeSpeechToText:
    def __init__(self, config: AppConfig) -> None:
        from RealtimeSTT import AudioToTextRecorder

        self._config = config
        try:
            self._recorder = AudioToTextRecorder(
                model=config.transcription_model,
                transcription_engine=config.transcription_engine,
                language=config.language,
                device=config.device,
                compute_type=config.compute_type,
                input_device_index=config.input_device_index,
                spinner=False,
                level=logging.DEBUG if config.debug else logging.WARNING,
                post_speech_silence_duration=config.post_speech_silence_duration,
                min_length_of_recording=config.min_length_of_recording,
                enable_realtime_transcription=config.realtime_transcription,
            )
        except Exception as exc:
            raise RuntimeError(
                "Speech-to-text initialization failed. Install the optional runtime "
                "packages with `python -m pip install faster-whisper silero-vad`, "
                "then retry. If audio input still fails, set `VOICE_MOD_INPUT_DEVICE_INDEX` "
                "to the correct microphone device."
            ) from exc

    def start_recording(self) -> None:
        LOGGER.info("listening")
        self._recorder.start()

    def stop_recording(self) -> None:
        self._recorder.stop()

    def transcribe_current_recording(self) -> TranscriptResult:
        LOGGER.info("transcribing")
        transcript = self._recorder.text()
        return normalize_transcript(transcript)

    def shutdown(self) -> None:
        self._recorder.shutdown()
