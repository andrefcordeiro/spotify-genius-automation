import os
import platform
import shlex
import shutil
import socket
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


BROWSER_ENV = "SPOTIFY_GENIUS_BROWSER"
BROWSER_PROFILE_ENV = "SPOTIFY_GENIUS_BROWSER_PROFILE"


@dataclass(frozen=True)
class BrowserSpec:
    command: tuple[str, ...]
    kind: str
    base_args: tuple[str, ...] = ()

    @property
    def executable(self) -> str:
        return self.command[0]


class DedicatedBrowserOpener:
    def __init__(self):
        self._window_started = False
        self._remote_debugging_port: int | None = None

    def open(self, url: str):
        if platform.system() == "Linux" and self._open_linux(url):
            return

        webbrowser.open(url)

    def _open_linux(self, url: str) -> bool:
        browser = _select_linux_browser()
        if browser is None:
            return False

        if (
            self._window_started
            and browser.kind == "chromium"
            and self._remote_debugging_port is not None
            and _open_chromium_tab(self._remote_debugging_port, url)
        ):
            return True

        profile_dir = _linux_profile_dir(browser)
        profile_dir.mkdir(parents=True, exist_ok=True)

        remote_debugging_port = None
        if browser.kind == "chromium" and not self._window_started:
            remote_debugging_port = _find_available_port()
            self._remote_debugging_port = remote_debugging_port

        args = _build_browser_args(
            browser,
            profile_dir,
            url,
            first_window=not self._window_started,
            remote_debugging_port=remote_debugging_port,
        )

        try:
            subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return False

        self._window_started = True
        return True


def open_url(url: str):
    _DEFAULT_OPENER.open(url)


def _select_linux_browser() -> BrowserSpec | None:
    env_browser = _browser_from_env()
    if env_browser is not None:
        return env_browser

    default_browser = _default_desktop_browser()
    if default_browser:
        default_browser_key = default_browser.lower()
        for command, kind, desktop_tokens in _LINUX_BROWSER_CANDIDATES:
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

    for command, kind, _ in _LINUX_BROWSER_CANDIDATES:
        executable = shutil.which(command)
        if executable:
            return BrowserSpec((executable,), kind)

    return None


def _browser_from_env() -> BrowserSpec | None:
    browser_command = os.environ.get(BROWSER_ENV, "").strip()
    if not browser_command:
        return None

    args = shlex.split(browser_command)
    if not args:
        return None

    executable = shutil.which(args[0]) or args[0]
    kind = _browser_kind_from_name(Path(executable).name)
    if kind is None:
        return None

    return BrowserSpec((executable,), kind, tuple(args[1:]))


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


def _browser_kind_from_name(name: str) -> str | None:
    normalized = name.lower()
    if "firefox" in normalized:
        return "firefox"
    if any(
        token in normalized
        for token in (
            "brave",
            "chrome",
            "chromium",
            "edge",
            "vivaldi",
        )
    ):
        return "chromium"
    return None


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


def _linux_profile_dir(browser: BrowserSpec) -> Path:
    configured_dir = os.environ.get(BROWSER_PROFILE_ENV, "").strip()
    if configured_dir:
        return Path(configured_dir).expanduser()

    cache_home = Path(os.environ.get("XDG_CACHE_HOME", "~/.cache")).expanduser()
    browser_name = Path(browser.executable).name
    return cache_home / "spotify-genius" / "browser-profile" / browser_name


def _build_browser_args(
    browser: BrowserSpec,
    profile_dir: Path,
    url: str,
    *,
    first_window: bool,
    remote_debugging_port: int | None = None,
) -> list[str]:
    if browser.kind == "firefox":
        command = [*browser.command, *browser.base_args]
        if first_window:
            return [
                *command,
                "--new-instance",
                "--profile",
                str(profile_dir),
                "--new-window",
                url,
            ]

        return [
            *command,
            "--profile",
            str(profile_dir),
            "--new-tab",
            url,
        ]

    command = [
        *browser.command,
        *browser.base_args,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
    ]
    if remote_debugging_port is not None:
        command.extend(
            [
                "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={remote_debugging_port}",
            ]
        )
    if first_window:
        command.append("--new-window")
    command.append(url)
    return command


def _find_available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _open_chromium_tab(remote_debugging_port: int, url: str) -> bool:
    request = Request(
        f"http://127.0.0.1:{remote_debugging_port}/json/new?{quote(url, safe='')}",
        method="PUT",
    )
    try:
        with urlopen(request, timeout=1) as response:
            return 200 <= response.status < 300
    except (OSError, URLError, TimeoutError):
        return False


_LINUX_BROWSER_CANDIDATES = (
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


_DEFAULT_OPENER = DedicatedBrowserOpener()
