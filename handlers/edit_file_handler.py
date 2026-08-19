from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from handlers.base import BaseHandler, HandlerResult

_EDITOR_CANDIDATES = ["code", "nvim", "vim", "nano"]


def _find_editor() -> str:
    env_editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if env_editor and shutil.which(env_editor):
        return env_editor
    for name in _EDITOR_CANDIDATES:
        if shutil.which(name):
            return name
    return "xdg-open"


class EditFileHandler(BaseHandler):
    """Opens a file in the user's preferred editor."""

    def __init__(self) -> None:
        self._editor = _find_editor()

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Open a file for editing. Use when the user says 'edit', 'open file', "
            "'modify', or wants to view/change a specific file."
        )

    def tool_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to open for editing.",
                },
                "create_if_missing": {
                    "type": "boolean",
                    "description": "If true, create the file if it doesn't exist. Defaults to false.",
                },
            },
            "required": ["file_path"],
        }

    def execute(self, **kwargs: Any) -> HandlerResult:
        file_path = kwargs.get("file_path", "").strip()
        create = kwargs.get("create_if_missing", False)

        if not file_path:
            return HandlerResult(success=False, output="No file path provided.", handler_name=self.name)

        path = Path(file_path).expanduser()

        if not path.exists():
            if create:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            else:
                return HandlerResult(
                    success=False,
                    output=f"File not found: {path}",
                    handler_name=self.name,
                )

        import subprocess
        try:
            subprocess.Popen(
                [self._editor, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return HandlerResult(
                success=True,
                output=f"Opened {path} in {self._editor}",
                handler_name=self.name,
                raw_args=kwargs,
            )
        except Exception as exc:
            return HandlerResult(success=False, output=f"Failed to open editor: {exc}", handler_name=self.name)
