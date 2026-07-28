from .common import BrowserSpec
from .opener import DedicatedBrowserOpener, open_url, window_closed

__all__ = ["BrowserSpec", "DedicatedBrowserOpener", "open_url", "window_closed"]
