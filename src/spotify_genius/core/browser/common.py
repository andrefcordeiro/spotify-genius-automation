import os
import platform
import shlex
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
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


def _browser_from_env() -> BrowserSpec | None:
    browser_command = os.environ.get(BROWSER_ENV, "").strip()
    if not browser_command:
        return None

    args = _split_command(browser_command)
    if not args:
        return None

    raw_executable = _strip_surrounding_quotes(args[0])
    executable = shutil.which(raw_executable) or raw_executable
    kind = _browser_kind_from_name(_executable_name(executable))
    if kind is None:
        return None

    return BrowserSpec((executable,), kind, tuple(args[1:]))


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


def _split_command(command: str) -> list[str]:
    return shlex.split(command, posix=platform.system() != "Windows")


def _strip_surrounding_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _executable_name(executable: str) -> str:
    if "\\" in executable or ":" in executable:
        return PureWindowsPath(executable).name
    return Path(executable).name


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
