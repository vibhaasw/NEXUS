from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from handlers.base import BaseHandler, HandlerResult

_FILLER = {
    "the",
    "a",
    "an",
    "my",
    "please",
    "app",
    "application",
    "for",
    "me",
    "on",
    "computer",
    "desktop",
    "now",
    "just",
}

_COMMON_ALIASES = {
    "code": "code",
    "vscode": "code",
    "vs code": "code",
    "chrome": "google-chrome-stable",
    "google chrome": "google-chrome-stable",
    "google-chrome": "google-chrome-stable",
    "firefox": "firefox",
    "brave": "brave",
    "brave browser": "brave",
    "chromium": "chromium",
    "spotify": "spotify",
    "terminal": "kitty",
    "kitty": "kitty",
    "files": "nautilus",
    "file manager": "nautilus",
}

# Well-known sites → canonical https URL. Unknown names fall back to https://<name>.com
_SITE_URLS = {
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "gitlab": "https://gitlab.com",
    "reddit": "https://www.reddit.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "whatsapp": "https://web.whatsapp.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "cursor": "https://cursor.com",
    "wikipedia": "https://www.wikipedia.org",
}

_BROWSER_NAMES = {
    "firefox",
    "chrome",
    "google chrome",
    "google-chrome",
    "google-chrome-stable",
    "brave",
    "brave browser",
    "chromium",
    "edge",
    "opera",
}


def _normalize_target(raw: str) -> str:
    text = raw.strip().strip("\"'.,!?")
    text = re.sub(r"\s+", " ", text)
    parts = [p for p in text.split(" ") if p.lower() not in _FILLER]
    return " ".join(parts).strip()


def resolve_url(raw: str) -> str | None:
    """Turn a site name, domain, or URL into an https URL."""
    text = raw.strip().strip("\"'")
    if not text:
        return None

    lower = text.lower()
    if lower in _SITE_URLS:
        return _SITE_URLS[lower]

    if re.match(r"^https?://", text, re.IGNORECASE):
        return text

    # domain-like: youtube.com, www.foo.org, foo.co.uk/path
    if re.match(r"^(www\.)?[a-z0-9.-]+\.[a-z]{2,}(/.*)?$", lower):
        return text if lower.startswith("http") else f"https://{text}"

    # bare site token → https://name.com when not a known local app
    if re.match(r"^[a-z0-9][a-z0-9-]*$", lower) and lower not in _COMMON_ALIASES and lower not in _BROWSER_NAMES:
        if lower in _SITE_URLS:
            return _SITE_URLS[lower]
        return f"https://www.{lower}.com"

    multi = " ".join(lower.split())
    if multi in _SITE_URLS:
        return _SITE_URLS[multi]

    return None


def parse_open_intent(raw: str) -> dict[str, str]:
    """
    Generic parse for open intents:
      - 'firefox'
      - 'https://example.com'
      - 'youtube in firefox'
      - 'firefox https://youtube.com'
      - 'github.com with chrome'
    Returns keys among: app, url, target
    """
    text = _normalize_target(raw)
    if not text:
        return {}

    lower = text.lower()

    # "<site|url> in|with|using <browser>"
    m = re.match(
        r"^(?P<what>.+?)\s+(?:in|with|using|via)\s+(?P<browser>.+)$",
        text,
        re.IGNORECASE,
    )
    if m:
        what = m.group("what").strip()
        browser = m.group("browser").strip()
        url = resolve_url(what)
        browser_known = (
            browser.lower() in _BROWSER_NAMES or bool(_COMMON_ALIASES.get(browser.lower()))
        )
        if url and browser_known:
            return {"app": browser, "url": url}
        if url:
            return {"app": browser, "url": url}

    # "<browser> <url|site>"
    parts = text.split(None, 1)
    if len(parts) == 2:
        first, rest = parts
        if first.lower() in _BROWSER_NAMES or _COMMON_ALIASES.get(first.lower()):
            url = resolve_url(rest) or (rest if rest.startswith(("http://", "https://")) else None)
            if url:
                return {"app": first, "url": url}
        # "site browser" rare; ignore

    if text.startswith(("http://", "https://", "/")):
        return {"url": text}

    url = resolve_url(text)
    # Prefer local app if name is a known app/browser; otherwise treat as URL site.
    if text.lower() in _COMMON_ALIASES or text.lower() in _BROWSER_NAMES:
        return {"app": text}
    if url and text.lower() not in _COMMON_ALIASES:
        # Ambiguous single token site vs app: if it's a known site, open URL in default handler.
        if text.lower() in _SITE_URLS or "." in text:
            return {"url": url}

    return {"app": text, "target": text}


def _candidate_names(target: str) -> list[str]:
    cleaned = _normalize_target(target)
    if not cleaned:
        return []

    lower = cleaned.lower()
    names: list[str] = []

    alias = _COMMON_ALIASES.get(lower)
    if alias:
        names.append(alias)

    names.append(lower)
    names.append(cleaned)
    names.append(lower.replace(" ", "-"))
    names.append(lower.replace(" ", ""))

    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        key = name.lower()
        if key and key not in seen:
            seen.add(key)
            ordered.append(name)
    return ordered


def _which_ci(name: str) -> str | None:
    direct = shutil.which(name)
    if direct:
        return direct
    direct = shutil.which(name.lower())
    if direct:
        return direct

    import os

    needle = name.lower()
    for directory in [p for p in os.environ.get("PATH", "").split(":") if p]:
        try:
            for entry in Path(directory).iterdir():
                if entry.name.lower() == needle and entry.is_file() and os.access(entry, os.X_OK):
                    return str(entry)
        except OSError:
            continue
    return None


def _desktop_file(name: str) -> Path | None:
    bases = [
        Path.home() / ".local/share/applications",
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path("/var/lib/flatpak/exports/share/applications"),
        Path.home() / ".local/share/flatpak/exports/share/applications",
    ]
    needle = name.lower().removesuffix(".desktop")
    for base in bases:
        if not base.is_dir():
            continue
        exact = base / f"{needle}.desktop"
        if exact.is_file():
            return exact
        try:
            for entry in base.glob("*.desktop"):
                if entry.stem.lower() == needle or needle in entry.stem.lower():
                    return entry
        except OSError:
            continue
    return None


class OpenAppHandler(BaseHandler):
    """Opens an application, URL, or URL inside a specific browser."""

    @property
    def name(self) -> str:
        return "open_app"

    @property
    def description(self) -> str:
        return (
            "Open an application, a website/URL, or a website inside a specific browser. "
            "Examples: open firefox; open https://github.com; open youtube in firefox; "
            "open github.com with chrome. Pass app and/or url when the user names both."
        )

    def tool_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": (
                        "Free-form open request, e.g. 'firefox', 'youtube in firefox', "
                        "'https://example.com'. Prefer separate app/url fields when possible."
                    ),
                },
                "app": {
                    "type": "string",
                    "description": "Application or browser name, e.g. 'firefox', 'chrome', 'spotify'.",
                },
                "url": {
                    "type": "string",
                    "description": (
                        "Website or URL to open, e.g. 'https://www.youtube.com' or 'github.com'. "
                        "Use with app when the user says 'open X in Y'."
                    ),
                },
            },
        }

    def execute(self, **kwargs: Any) -> HandlerResult:
        app = (kwargs.get("app") or "").strip()
        url = (kwargs.get("url") or "").strip()
        target = (kwargs.get("target") or "").strip()

        if not app and not url and target:
            parsed = parse_open_intent(target)
            app = parsed.get("app", "")
            url = parsed.get("url", "")
            if not app and not url:
                app = parsed.get("target", target)

        if url and not url.startswith(("http://", "https://")):
            url = resolve_url(url) or url

        if app and url:
            return self._open_url_in_app(app, url)

        if url and not app:
            return self._xdg_open(url)

        if app:
            return self._launch_app(app)

        return HandlerResult(success=False, output="No target specified.", handler_name=self.name)

    def _open_url_in_app(self, app: str, url: str) -> HandlerResult:
        for candidate in _candidate_names(app):
            app_path = _which_ci(candidate)
            if app_path:
                try:
                    subprocess.Popen(
                        [app_path, url],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                    return HandlerResult(
                        success=True,
                        output=f"Opened {url} in {candidate}",
                        handler_name=self.name,
                        raw_args={"app": candidate, "url": url, "path": app_path},
                    )
                except Exception as exc:
                    return HandlerResult(
                        success=False,
                        output=f"Failed to open {url} in {candidate}: {exc}",
                        handler_name=self.name,
                        raw_args={"app": candidate, "url": url},
                    )

        # Browser missing → still try default opener for the URL.
        opened = self._xdg_open(url)
        if opened.success:
            opened.output = f"{opened.output} (browser '{app}' not found; used default)"
            opened.raw_args = {"app": app, "url": url, "fallback": "xdg-open"}
        return opened

    def _launch_app(self, target: str) -> HandlerResult:
        # Combined strings like "firefox https://..." still handled here.
        parsed = parse_open_intent(target)
        if parsed.get("app") and parsed.get("url"):
            return self._open_url_in_app(parsed["app"], parsed["url"])
        if parsed.get("url") and not parsed.get("app"):
            return self._xdg_open(parsed["url"])

        name = parsed.get("app") or target
        for candidate in _candidate_names(name):
            app_path = _which_ci(candidate)
            if app_path:
                return self._launch_detached(app_path, candidate)

            desktop = _desktop_file(candidate)
            if desktop:
                launched = self._gtk_launch(desktop.stem)
                if launched.success:
                    return launched
                return self._xdg_open(str(desktop))

        return HandlerResult(
            success=False,
            output=(
                f"Could not find an app named '{_normalize_target(name) or name}'. "
                "Try the exact binary name (e.g. 'spotify', 'firefox')."
            ),
            handler_name=self.name,
            raw_args={"target": target},
        )

    def _gtk_launch(self, desktop_id: str) -> HandlerResult:
        if not shutil.which("gtk-launch"):
            return HandlerResult(success=False, output="gtk-launch not found.", handler_name=self.name)
        try:
            subprocess.Popen(
                ["gtk-launch", desktop_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return HandlerResult(
                success=True,
                output=f"Launched: {desktop_id}",
                handler_name=self.name,
                raw_args={"target": desktop_id},
            )
        except Exception as exc:
            return HandlerResult(
                success=False,
                output=f"Failed to gtk-launch {desktop_id}: {exc}",
                handler_name=self.name,
            )

    def _xdg_open(self, target: str) -> HandlerResult:
        try:
            subprocess.Popen(
                ["xdg-open", target],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
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
                raw_args={"target": display_name, "path": app_path},
            )
        except Exception as exc:
            return HandlerResult(
                success=False,
                output=f"Failed to launch {display_name}: {exc}",
                handler_name=self.name,
            )
