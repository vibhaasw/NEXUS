from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RecordingSession:
    started: bool = False


class AudioController:
    """Small state helper around the recorder lifecycle."""

    def __init__(self) -> None:
        self.session = RecordingSession()

    def mark_started(self) -> None:
        self.session.started = True

    def mark_stopped(self) -> None:
        self.session.started = False

    def is_recording(self) -> bool:
        return self.session.started
