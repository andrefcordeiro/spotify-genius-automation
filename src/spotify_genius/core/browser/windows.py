import os
import shutil
from pathlib import Path

from .common import (
    BROWSER_PROFILE_ENV,
    BrowserSpec,
    _browser_from_env,
    _executable_name,
)


def select_browser() -> BrowserSpec | None:
    env_browser = _browser_from_env()
    if env_browser is not None:
        return env_browser

    default_browser = _default_windows_browser()
    if default_browser:
        default_browser_key = default_browser.lower()
        for executable_name, kind, browser_tokens in WINDOWS_BROWSER_CANDIDATES:
            if any(token in default_browser_key for token in browser_tokens):
                executable = _find_windows_executable(executable_name)
                if executable:
                    return BrowserSpec((executable,), kind)

    for executable_name, kind, _ in WINDOWS_BROWSER_CANDIDATES:
        executable = _find_windows_executable(executable_name)
        if executable:
            return BrowserSpec((executable,), kind)

    return None


def profile_dir(browser: BrowserSpec) -> Path:
    configured_dir = os.environ.get(BROWSER_PROFILE_ENV, "").strip()
    if configured_dir:
        return Path(configured_dir).expanduser()

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base_dir = Path(local_app_data)
    else:
        base_dir = Path.home() / "AppData" / "Local"

    browser_name = _executable_name(browser.executable)
    return base_dir / "SpotifyGenius" / "BrowserProfile" / browser_name


def _default_windows_browser() -> str | None:
    try:
        import winreg
    except ImportError:
        return None

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "ProgId")
            return value or None
    except OSError:
        return None


def _find_windows_executable(executable_name: str) -> str | None:
    executable = shutil.which(executable_name)
    if executable:
        return executable

    executable = _windows_app_path(executable_name)
    if executable:
        return executable

    for candidate in _windows_common_browser_paths(executable_name):
        if candidate.is_file():
            return str(candidate)

    return None


def _windows_app_path(executable_name: str) -> str | None:
    try:
        import winreg
    except ImportError:
        return None

    subkey = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{executable_name}"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _ = winreg.QueryValueEx(key, "")
                if value:
                    return value
        except OSError:
            continue

    return None


def _windows_common_browser_paths(executable_name: str) -> tuple[Path, ...]:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))

    paths = {
        "chrome.exe": (
            program_files / "Google" / "Chrome" / "Application" / executable_name,
            program_files_x86 / "Google" / "Chrome" / "Application" / executable_name,
            local_app_data / "Google" / "Chrome" / "Application" / executable_name,
        ),
        "msedge.exe": (
            program_files / "Microsoft" / "Edge" / "Application" / executable_name,
            program_files_x86 / "Microsoft" / "Edge" / "Application" / executable_name,
        ),
        "brave.exe": (
            program_files / "BraveSoftware" / "Brave-Browser" / "Application" / executable_name,
            program_files_x86 / "BraveSoftware" / "Brave-Browser" / "Application" / executable_name,
            local_app_data / "BraveSoftware" / "Brave-Browser" / "Application" / executable_name,
        ),
        "vivaldi.exe": (
            program_files / "Vivaldi" / "Application" / executable_name,
            local_app_data / "Vivaldi" / "Application" / executable_name,
        ),
        "firefox.exe": (
            program_files / "Mozilla Firefox" / executable_name,
            program_files_x86 / "Mozilla Firefox" / executable_name,
        ),
    }
    return paths.get(executable_name.lower(), ())


WINDOWS_BROWSER_CANDIDATES = (
    ("chrome.exe", "chromium", ("chrome", "chromehtml", "google")),
    ("msedge.exe", "chromium", ("edge", "msedge", "microsoft")),
    ("brave.exe", "chromium", ("brave",)),
    ("vivaldi.exe", "chromium", ("vivaldi",)),
    ("firefox.exe", "firefox", ("firefox", "mozilla")),
)
