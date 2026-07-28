import os
import shlex
import shutil
import subprocess
from pathlib import Path

from .common import (
    BROWSER_PROFILE_ENV,
    BrowserSpec,
    _browser_from_env,
    _browser_kind_from_name,
    _executable_name,
)


def select_browser() -> BrowserSpec | None:
    env_browser = _browser_from_env()
    if env_browser is not None:
        return env_browser

    default_browser = _default_desktop_browser()
    if default_browser:
        default_browser_key = default_browser.lower()
        for command, kind, desktop_tokens in LINUX_BROWSER_CANDIDATES:
            if any(token in default_browser_key for token in desktop_tokens):
                executable = shutil.which(command)
                if executable:
                    return BrowserSpec((executable,), kind)

        desktop_browser = _browser_from_desktop_file(default_browser)
        if desktop_browser is not None:
            return desktop_browser

        flatpak_browser = _browser_from_flatpak_app_id(default_browser)
        if flatpak_browser is not None:
            return flatpak_browser

    for command, kind, _ in LINUX_BROWSER_CANDIDATES:
        executable = shutil.which(command)
        if executable:
            return BrowserSpec((executable,), kind)

    return None


def profile_dir(browser: BrowserSpec) -> Path:
    configured_dir = os.environ.get(BROWSER_PROFILE_ENV, "").strip()
    if configured_dir:
        return Path(configured_dir).expanduser()

    cache_home = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser()
    browser_name = _executable_name(browser.executable)
    return cache_home / "spotify-genius" / "browser-profile" / browser_name


def _default_desktop_browser() -> str | None:
    try:
        result = subprocess.run(
            ["xdg-settings", "get", "default-web-browser"],
            capture_output=True,
            check=False,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    return result.stdout.strip() or None


def _browser_from_desktop_file(desktop_file: str) -> BrowserSpec | None:
    desktop_path = _find_desktop_file(desktop_file)
    if desktop_path is None:
        return None

    try:
        contents = desktop_path.read_text(encoding="utf-8")
    except OSError:
        return None

    exec_line = None
    for line in contents.splitlines():
        if line.startswith("Exec="):
            exec_line = line.removeprefix("Exec=").strip()
            break

    if not exec_line:
        return None

    try:
        args = shlex.split(exec_line)
    except ValueError:
        return None

    command = _clean_desktop_exec_args(args)
    if not command:
        return None

    executable = shutil.which(command[0])
    if executable is None:
        return None

    kind = _browser_kind_from_name(" ".join((desktop_file, *command)))
    if kind is None:
        return None

    return BrowserSpec((executable, *command[1:]), kind)


def _browser_from_flatpak_app_id(desktop_file: str) -> BrowserSpec | None:
    if not desktop_file.endswith(".desktop"):
        return None

    flatpak = shutil.which("flatpak")
    if flatpak is None:
        return None

    app_id = desktop_file.removesuffix(".desktop")
    kind = _browser_kind_from_name(app_id)
    if kind is None:
        return None

    try:
        result = subprocess.run(
            [flatpak, "info", app_id],
            capture_output=True,
            check=False,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    return BrowserSpec((flatpak, "run", app_id), kind)


def _find_desktop_file(desktop_file: str) -> Path | None:
    data_dirs = [
        Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser(),
        *(Path(path) for path in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")),
    ]

    for data_dir in data_dirs:
        candidate = data_dir / "applications" / desktop_file
        if candidate.is_file():
            return candidate

    return None


def _clean_desktop_exec_args(args: list[str]) -> tuple[str, ...]:
    cleaned = []
    for arg in args:
        if arg in ("@@", "@@u", "@@U", "--file-forwarding"):
            continue
        if arg.startswith("%") and len(arg) == 2:
            continue
        cleaned.append(arg)

    return tuple(cleaned)


LINUX_BROWSER_CANDIDATES = (
    ("google-chrome", "chromium", ("google-chrome", "chrome")),
    ("google-chrome-stable", "chromium", ("google-chrome", "chrome")),
    ("chromium", "chromium", ("chromium",)),
    ("chromium-browser", "chromium", ("chromium",)),
    ("brave-browser", "chromium", ("brave",)),
    ("microsoft-edge", "chromium", ("microsoft-edge", "edge")),
    ("microsoft-edge-stable", "chromium", ("microsoft-edge", "edge")),
    ("vivaldi", "chromium", ("vivaldi",)),
    ("vivaldi-stable", "chromium", ("vivaldi",)),
    ("firefox", "firefox", ("firefox",)),
)
