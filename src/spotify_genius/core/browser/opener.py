import platform
import subprocess
import webbrowser

from . import linux, windows
from .common import (
    _build_browser_args,
    _chromium_has_open_pages,
    _find_available_port,
    _open_chromium_tab,
)


_CHROMIUM_CLOSED_CONFIRMATIONS = 3


class DedicatedBrowserOpener:
    def __init__(self):
        self._window_started = False
        self._browser_kind: str | None = None
        self._browser_process = None
        self._remote_debugging_port: int | None = None
        self._chromium_devtools_seen = False
        self._chromium_absent_checks = 0

    def open(self, url: str):
        system = platform.system()
        if system == "Linux" and self._open_platform(url, linux.select_browser, linux.profile_dir):
            return
        if system == "Windows" and self._open_platform(url, windows.select_browser, windows.profile_dir):
            return

        webbrowser.open(url)

    def window_closed(self) -> bool:
        if not self._window_started:
            return False

        if self._browser_kind == "chromium" and self._remote_debugging_port is not None:
            has_open_pages = _chromium_has_open_pages(self._remote_debugging_port)
            if has_open_pages is True:
                self._chromium_devtools_seen = True
                self._chromium_absent_checks = 0
                return False

            if not self._chromium_devtools_seen:
                return False

            self._chromium_absent_checks += 1
            return self._chromium_absent_checks >= _CHROMIUM_CLOSED_CONFIRMATIONS

        return self._browser_process is not None and self._browser_process.poll() is not None

    def _open_platform(self, url: str, select_browser, profile_dir_for) -> bool:
        browser = select_browser()
        if browser is None:
            return False

        if self._window_started and browser.kind == "chromium":
            if (
                self._remote_debugging_port is not None
                and _open_chromium_tab(self._remote_debugging_port, url)
            ):
                self._chromium_devtools_seen = True
                self._chromium_absent_checks = 0
                return True

            self._window_started = False
            self._remote_debugging_port = None
            self._chromium_devtools_seen = False
            self._chromium_absent_checks = 0

        profile_dir = profile_dir_for(browser)
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
            self._browser_process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return False

        self._window_started = True
        self._browser_kind = browser.kind
        if browser.kind == "chromium" and remote_debugging_port is not None:
            self._chromium_devtools_seen = False
            self._chromium_absent_checks = 0
        return True


def open_url(url: str):
    _DEFAULT_OPENER.open(url)


def window_closed() -> bool:
    return _DEFAULT_OPENER.window_closed()


_DEFAULT_OPENER = DedicatedBrowserOpener()
