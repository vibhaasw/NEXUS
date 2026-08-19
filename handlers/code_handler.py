from __future__ import annotations

import shutil
import subprocess
from typing import Any

from handlers.base import BaseHandler, HandlerResult

_CODE_CLI_CANDIDATES = ["opencode", "claude"]


def _find_code_cli() -> str | None:
    for name in _CODE_CLI_CANDIDATES:
        if shutil.which(name):
            return name
    return None


class CodeHandler(BaseHandler):
    """Dispatches coding tasks to an external code CLI (opencode / claude)."""

    def __init__(self) -> None:
        self._cli = _find_code_cli()

    @property
    def name(self) -> str:
        return "run_code_task"

    @property
    def description(self) -> str:
        return (
            "Run a coding task: write code, debug, refactor, explain code, generate a script, "
            "or any software-engineering request. This delegates to a local AI coding CLI."
        )

    def tool_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The coding task or question to send to the code assistant.",
                },
                "working_directory": {
                    "type": "string",
                    "description": "Optional directory to run in. Defaults to the current directory.",
                },
            },
            "required": ["prompt"],
        }

    def execute(self, **kwargs: Any) -> HandlerResult:
        prompt = kwargs.get("prompt", "")
        cwd = kwargs.get("working_directory") or None

        if not prompt.strip():
            return HandlerResult(success=False, output="No coding prompt provided.", handler_name=self.name)

        if not self._cli:
            return HandlerResult(
                success=False,
                output=(
                    "No code CLI found. Install 'opencode' or 'claude' (Claude Code CLI) "
                    "and make sure it is on your PATH."
                ),
                handler_name=self.name,
            )

        try:
            result = subprocess.run(
                [self._cli, prompt],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=cwd,
            )
            output = (result.stdout or "") + (result.stderr or "")
            return HandlerResult(
                success=result.returncode == 0,
                output=output.strip() or "(no output)",
                handler_name=self.name,
                raw_args=kwargs,
            )
        except subprocess.TimeoutExpired:
            return HandlerResult(success=False, output="Code task timed out after 120s.", handler_name=self.name)
        except FileNotFoundError:
            return HandlerResult(
                success=False,
                output=f"CLI '{self._cli}' not found at execution time.",
                handler_name=self.name,
            )
