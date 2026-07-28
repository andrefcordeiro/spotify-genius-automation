import platform
import subprocess
import webbrowser

from . import linux, windows
from .common import (
    _build_browser_args,
    _find_available_port,
    _open_chromium_tab,
)


class DedicatedBrowserOpener:
    def __init__(self):
        self._window_started = False
        self._remote_debugging_port: int | None = None

    def open(self, url: str):
        system = platform.system()
        if system == "Linux" and self._open_platform(url, linux.select_browser, linux.profile_dir):
            return
        if system == "Windows" and self._open_platform(url, windows.select_browser, windows.profile_dir):
            return

        webbrowser.open(url)

    def _open_platform(self, url: str, select_browser, profile_dir_for) -> bool:
        browser = select_browser()
        if browser is None:
            return False

        if (
            self._window_started
            and browser.kind == "chromium"
            and self._remote_debugging_port is not None
            and _open_chromium_tab(self._remote_debugging_port, url)
        ):
            return True

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


_DEFAULT_OPENER = DedicatedBrowserOpener()
