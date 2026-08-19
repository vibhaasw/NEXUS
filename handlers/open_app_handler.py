from __future__ import annotations

import shutil
import subprocess
from typing import Any

from handlers.base import BaseHandler, HandlerResult


class OpenAppHandler(BaseHandler):
    """Opens an application or file on the local machine."""

    @property
    def name(self) -> str:
        return "open_app"

    @property
    def description(self) -> str:
        return (
            "Open an application, URL, or file on the local machine. "
            "Use when the user says 'open firefox', 'launch terminal', 'open this file', etc."
        )

    def tool_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": (
                        "What to open: an application name (e.g. 'firefox', 'nautilus', 'code'), "
                        "a URL (e.g. 'https://github.com'), or a file path."
                    ),
                },
            },
            "required": ["target"],
        }

    def execute(self, **kwargs: Any) -> HandlerResult:
        target = kwargs.get("target", "").strip()
        if not target:
            return HandlerResult(success=False, output="No target specified.", handler_name=self.name)

        if target.startswith(("http://", "https://", "/")):
            return self._xdg_open(target)

        app_path = shutil.which(target)
        if app_path:
            return self._launch_detached(app_path, target)

        return self._xdg_open(target)

    def _xdg_open(self, target: str) -> HandlerResult:
        try:
            subprocess.Popen(
                ["xdg-open", target],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return HandlerResult(
                success=True,
                output=f"Opened: {target}",
                handler_name=self.name,
                raw_args={"target": target},
            )
        except FileNotFoundError:
            return HandlerResult(success=False, output="xdg-open not found.", handler_name=self.name)

    def _launch_detached(self, app_path: str, display_name: str) -> HandlerResult:
        try:
            subprocess.Popen(
                [app_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return HandlerResult(
                success=True,
                output=f"Launched: {display_name}",
                handler_name=self.name,
                raw_args={"target": display_name},
            )
        except Exception as exc:
            return HandlerResult(success=False, output=f"Failed to launch {display_name}: {exc}", handler_name=self.name)
