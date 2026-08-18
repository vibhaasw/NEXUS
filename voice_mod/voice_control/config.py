from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(slots=True)
class AppConfig:
    ollama_model: str = field(default_factory=lambda: os.getenv("VOICE_MOD_OLLAMA_MODEL", "phi4-mini:latest"))
    ollama_host: str | None = field(default_factory=lambda: os.getenv("OLLAMA_HOST"))
    system_prompt_mode: str = field(default_factory=lambda: os.getenv("VOICE_MOD_PROMPT_MODE", "router"))
    language: str = field(default_factory=lambda: os.getenv("VOICE_MOD_LANGUAGE", "en"))
    transcription_model: str = field(default_factory=lambda: os.getenv("VOICE_MOD_STT_MODEL", "tiny"))
    transcription_engine: str = field(default_factory=lambda: os.getenv("VOICE_MOD_STT_ENGINE", "faster_whisper"))
    device: str = field(default_factory=lambda: os.getenv("VOICE_MOD_DEVICE", "cpu"))
    compute_type: str = field(default_factory=lambda: os.getenv("VOICE_MOD_COMPUTE_TYPE", "default"))
    input_device_index: int | None = field(default_factory=lambda: _optional_int(os.getenv("VOICE_MOD_INPUT_DEVICE_INDEX")))
    post_speech_silence_duration: float = field(
        default_factory=lambda: float(os.getenv("VOICE_MOD_POST_SPEECH_SILENCE", "0.6"))
    )
    min_length_of_recording: float = field(
        default_factory=lambda: float(os.getenv("VOICE_MOD_MIN_RECORDING_LENGTH", "0.4"))
    )
    realtime_transcription: bool = field(
        default_factory=lambda: _parse_bool(os.getenv("VOICE_MOD_REALTIME_TRANSCRIPTION"), default=False)
    )
    debug: bool = field(default_factory=lambda: _parse_bool(os.getenv("VOICE_MOD_DEBUG"), default=False))


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def load_config() -> AppConfig:
    return AppConfig()
