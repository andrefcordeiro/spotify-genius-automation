import unittest
from pathlib import Path
from unittest.mock import patch

from spotify_genius.core.browser import (
    BrowserSpec,
    DedicatedBrowserOpener,
)
from spotify_genius import main
from spotify_genius.core.browser.common import (
    _build_browser_args,
    _browser_from_env,
    _split_command,
)
from spotify_genius.core.browser.linux import (
    _browser_from_flatpak_app_id,
    _clean_desktop_exec_args,
)
from spotify_genius.core.browser.windows import (
    profile_dir as _windows_profile_dir,
    select_browser as _select_windows_browser,
)
from spotify_genius.core.genius import (
    build_search_queries,
    remove_features,
    select_best_candidate,
    strip_version_tags,
)


class GeniusMatchingTests(unittest.TestCase):
    def test_remove_features_handles_parentheses_and_brackets(self):
        self.assertEqual(remove_features("Song Title (feat. Artist)"), "Song Title")
        self.assertEqual(remove_features("Song Title [ft. Artist]"), "Song Title")

    def test_strip_version_tags_removes_release_suffixes(self):
        self.assertEqual(strip_version_tags("Song Title - Remastered 2012"), "Song Title")
        self.assertEqual(strip_version_tags("Song Title (Live at Wembley)"), "Song Title")

    def test_build_search_queries_keeps_symbol_only_titles(self):
        queries = build_search_queries("Bring Me The Horizon", "¿")
        self.assertIn("Bring Me The Horizon ¿", queries)
        self.assertIn("¿ Bring Me The Horizon", queries)

    def test_select_best_candidate_prefers_exact_unicode_match(self):
        hits = [
            {
                "result": {
                    "title": "mother tongue",
                    "title_with_featured": "mother tongue",
                    "primary_artist": {"name": "Bring Me The Horizon"},
                    "url": "https://genius.com/Bring-me-the-horizon-mother-tongue-lyrics",
                }
            },
            {
                "result": {
                    "title": "¿",
                    "title_with_featured": "¿",
                    "primary_artist": {"name": "Bring Me The Horizon"},
                    "url": "https://genius.com/Bring-me-the-horizon-lyrics",
                }
            },
        ]

        candidate = select_best_candidate("Bring Me The Horizon", "¿", hits)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.url, "https://genius.com/Bring-me-the-horizon-lyrics")

    def test_select_best_candidate_rejects_low_confidence_matches(self):
        hits = [
            {
                "result": {
                    "title": "Medicine",
                    "title_with_featured": "Medicine",
                    "primary_artist": {"name": "Daughter"},
                    "url": "https://genius.com/Bring-me-the-horizon-medicine-lyrics",
                }
            },
            {
                "result": {
                    "title": "Parasite Eve",
                    "title_with_featured": "Parasite Eve",
                    "primary_artist": {"name": "Bring Me The Horizon"},
                    "url": "https://genius.com/Bring-me-the-horizon-parasite-eve-lyrics",
                }
            },
        ]

        candidate = select_best_candidate("Bring Me The Horizon", "Medicine", hits)

        self.assertIsNone(candidate)


class DedicatedBrowserOpenerTests(unittest.TestCase):
    def test_chromium_args_open_first_url_in_window_then_next_urls_as_tabs(self):
        browser = BrowserSpec(("/usr/bin/google-chrome",), "chromium")
        profile_dir = Path("/tmp/spotify-genius-test-profile")

        first = _build_browser_args(
            browser,
            profile_dir,
            "https://genius.com/first",
            first_window=True,
            remote_debugging_port=9222,
        )
        second = _build_browser_args(
            browser,
            profile_dir,
            "https://genius.com/second",
            first_window=False,
        )

        self.assertIn(f"--user-data-dir={profile_dir}", first)
        self.assertIn("--remote-debugging-address=127.0.0.1", first)
        self.assertIn("--remote-debugging-port=9222", first)
        self.assertIn("--new-window", first)
        self.assertEqual(first[-1], "https://genius.com/first")
        self.assertIn(f"--user-data-dir={profile_dir}", second)
        self.assertNotIn("--new-window", second)
        self.assertEqual(second[-1], "https://genius.com/second")

    def test_firefox_args_open_first_url_in_window_then_next_urls_as_tabs(self):
        browser = BrowserSpec(("/usr/bin/firefox",), "firefox")
        profile_dir = Path("/tmp/spotify-genius-test-profile")

        first = _build_browser_args(
            browser,
            profile_dir,
            "https://genius.com/first",
            first_window=True,
        )
        second = _build_browser_args(
            browser,
            profile_dir,
            "https://genius.com/second",
            first_window=False,
        )

        self.assertIn("--new-instance", first)
        self.assertIn("--new-window", first)
        self.assertEqual(first[-1], "https://genius.com/first")
        self.assertNotIn("--new-instance", second)
        self.assertIn("--new-tab", second)
        self.assertEqual(second[-1], "https://genius.com/second")

    @patch("spotify_genius.core.browser.opener.platform.system", return_value="Linux")
    @patch(
        "spotify_genius.core.browser.opener.linux.profile_dir",
        return_value=Path("/tmp/spotify-genius-test-profile"),
    )
    @patch(
        "spotify_genius.core.browser.opener.linux.select_browser",
        return_value=BrowserSpec(("/usr/bin/google-chrome",), "chromium"),
    )
    @patch("spotify_genius.core.browser.opener._open_chromium_tab", return_value=True)
    @patch("spotify_genius.core.browser.opener._find_available_port", return_value=9222)
    @patch("spotify_genius.core.browser.opener.subprocess.Popen")
    def test_linux_chromium_opener_adds_later_urls_through_existing_window(
        self,
        popen,
        _find_port,
        open_chromium_tab,
        _select_browser,
        _profile_dir,
        _system,
    ):
        opener = DedicatedBrowserOpener()

        opener.open("https://genius.com/first")
        opener.open("https://genius.com/second")

        popen.assert_called_once()
        first_args = popen.call_args.args[0]
        self.assertIn("--new-window", first_args)
        self.assertIn("--remote-debugging-port=9222", first_args)
        self.assertEqual(first_args[-1], "https://genius.com/first")
        open_chromium_tab.assert_called_once_with(9222, "https://genius.com/second")

    @patch("spotify_genius.core.browser.opener.platform.system", return_value="Linux")
    @patch(
        "spotify_genius.core.browser.opener.linux.profile_dir",
        return_value=Path("/tmp/spotify-genius-test-profile"),
    )
    @patch(
        "spotify_genius.core.browser.opener.linux.select_browser",
        return_value=BrowserSpec(("/usr/bin/google-chrome",), "chromium"),
    )
    @patch("spotify_genius.core.browser.opener._open_chromium_tab", return_value=False)
    @patch("spotify_genius.core.browser.opener._find_available_port", side_effect=[9222, 9333])
    @patch("spotify_genius.core.browser.opener.subprocess.Popen")
    def test_linux_chromium_opener_restarts_dedicated_window_when_tab_attach_fails(
        self,
        popen,
        _find_port,
        open_chromium_tab,
        _select_browser,
        _profile_dir,
        _system,
    ):
        opener = DedicatedBrowserOpener()

        opener.open("https://genius.com/first")
        opener.open("https://genius.com/second")

        self.assertEqual(popen.call_count, 2)
        first_args = popen.call_args_list[0].args[0]
        second_args = popen.call_args_list[1].args[0]
        self.assertIn("--new-window", first_args)
        self.assertIn("--remote-debugging-port=9222", first_args)
        self.assertEqual(first_args[-1], "https://genius.com/first")
        self.assertIn("--new-window", second_args)
        self.assertIn("--remote-debugging-port=9333", second_args)
        self.assertEqual(second_args[-1], "https://genius.com/second")
        open_chromium_tab.assert_called_once_with(9222, "https://genius.com/second")

    @patch("spotify_genius.core.browser.opener._chromium_has_open_pages", return_value=False)
    def test_chromium_window_is_closed_when_devtools_has_no_pages(self, has_open_pages):
        opener = DedicatedBrowserOpener()
        opener._window_started = True
        opener._browser_kind = "chromium"
        opener._remote_debugging_port = 9222
        opener._chromium_devtools_seen = True

        self.assertFalse(opener.window_closed())
        self.assertFalse(opener.window_closed())
        self.assertTrue(opener.window_closed())
        self.assertEqual(has_open_pages.call_count, 3)

    @patch("spotify_genius.core.browser.opener._chromium_has_open_pages", return_value=True)
    def test_chromium_window_is_not_closed_when_devtools_has_pages(self, has_open_pages):
        opener = DedicatedBrowserOpener()
        opener._window_started = True
        opener._browser_kind = "chromium"
        opener._remote_debugging_port = 9222

        self.assertFalse(opener.window_closed())
        has_open_pages.assert_called_once_with(9222)

    @patch("spotify_genius.core.browser.opener._chromium_has_open_pages", return_value=None)
    def test_chromium_window_is_not_closed_when_devtools_is_not_ready(self, has_open_pages):
        opener = DedicatedBrowserOpener()
        opener._window_started = True
        opener._browser_kind = "chromium"
        opener._remote_debugging_port = 9222

        self.assertFalse(opener.window_closed())
        self.assertFalse(opener.window_closed())
        self.assertEqual(has_open_pages.call_count, 2)

    @patch(
        "spotify_genius.core.browser.opener._chromium_has_open_pages",
        side_effect=[True, None, None, None],
    )
    def test_chromium_window_is_closed_after_devtools_disappears(self, has_open_pages):
        opener = DedicatedBrowserOpener()
        opener._window_started = True
        opener._browser_kind = "chromium"
        opener._remote_debugging_port = 9222

        self.assertFalse(opener.window_closed())
        self.assertFalse(opener.window_closed())
        self.assertFalse(opener.window_closed())
        self.assertTrue(opener.window_closed())
        self.assertEqual(has_open_pages.call_count, 4)

    @patch("spotify_genius.main.time.sleep")
    @patch("spotify_genius.main.get_current_song", return_value=(None, None))
    @patch("spotify_genius.main.genius_window_closed", side_effect=[False, True])
    @patch("builtins.print")
    def test_main_loop_exits_when_genius_window_is_closed(
        self,
        _print,
        genius_window_closed,
        _get_current_song,
        _sleep,
    ):
        main.run()

        self.assertEqual(genius_window_closed.call_count, 2)

    @patch("spotify_genius.core.browser.opener.platform.system", return_value="Linux")
    @patch(
        "spotify_genius.core.browser.opener.linux.profile_dir",
        return_value=Path("/tmp/spotify-genius-test-profile"),
    )
    @patch(
        "spotify_genius.core.browser.opener.linux.select_browser",
        return_value=BrowserSpec(("/usr/bin/firefox",), "firefox"),
    )
    @patch("spotify_genius.core.browser.opener.subprocess.Popen")
    def test_linux_firefox_opener_uses_new_window_then_new_tab_args(
        self,
        popen,
        _select_browser,
        _profile_dir,
        _system,
    ):
        opener = DedicatedBrowserOpener()

        opener.open("https://genius.com/first")
        opener.open("https://genius.com/second")

        self.assertEqual(popen.call_count, 2)
        first_args = popen.call_args_list[0].args[0]
        second_args = popen.call_args_list[1].args[0]
        self.assertIn("--new-window", first_args)
        self.assertIn("--new-tab", second_args)
        self.assertEqual(first_args[-1], "https://genius.com/first")
        self.assertEqual(second_args[-1], "https://genius.com/second")

    @patch("spotify_genius.core.browser.opener.platform.system", return_value="Linux")
    @patch("spotify_genius.core.browser.opener.linux.select_browser", return_value=None)
    @patch("spotify_genius.core.browser.opener.webbrowser.open")
    def test_linux_opener_falls_back_to_webbrowser_when_no_supported_browser_is_found(
        self,
        webbrowser_open,
        _select_browser,
        _system,
    ):
        DedicatedBrowserOpener().open("https://genius.com/fallback")

        webbrowser_open.assert_called_once_with("https://genius.com/fallback")

    @patch("spotify_genius.core.browser.opener.platform.system", return_value="Windows")
    @patch(
        "spotify_genius.core.browser.opener.windows.profile_dir",
        return_value=Path(r"C:\Users\Andre\AppData\Local\SpotifyGenius\BrowserProfile\chrome.exe"),
    )
    @patch(
        "spotify_genius.core.browser.opener.windows.select_browser",
        return_value=BrowserSpec((r"C:\Program Files\Google\Chrome\Application\chrome.exe",), "chromium"),
    )
    @patch("spotify_genius.core.browser.opener._open_chromium_tab", return_value=True)
    @patch("spotify_genius.core.browser.opener._find_available_port", return_value=9222)
    @patch("spotify_genius.core.browser.opener.subprocess.Popen")
    def test_windows_chromium_opener_adds_later_urls_through_existing_window(
        self,
        popen,
        _find_port,
        open_chromium_tab,
        _select_browser,
        _profile_dir,
        _system,
    ):
        opener = DedicatedBrowserOpener()

        opener.open("https://genius.com/first")
        opener.open("https://genius.com/second")

        popen.assert_called_once()
        first_args = popen.call_args.args[0]
        self.assertIn("--new-window", first_args)
        self.assertIn("--remote-debugging-port=9222", first_args)
        self.assertEqual(first_args[-1], "https://genius.com/first")
        open_chromium_tab.assert_called_once_with(9222, "https://genius.com/second")

    @patch("spotify_genius.core.browser.opener.platform.system", return_value="Windows")
    @patch(
        "spotify_genius.core.browser.opener.windows.profile_dir",
        return_value=Path(r"C:\Users\Andre\AppData\Local\SpotifyGenius\BrowserProfile\firefox.exe"),
    )
    @patch(
        "spotify_genius.core.browser.opener.windows.select_browser",
        return_value=BrowserSpec((r"C:\Program Files\Mozilla Firefox\firefox.exe",), "firefox"),
    )
    @patch("spotify_genius.core.browser.opener.subprocess.Popen")
    def test_windows_firefox_opener_uses_new_window_then_new_tab_args(
        self,
        popen,
        _select_browser,
        _profile_dir,
        _system,
    ):
        opener = DedicatedBrowserOpener()

        opener.open("https://genius.com/first")
        opener.open("https://genius.com/second")

        self.assertEqual(popen.call_count, 2)
        first_args = popen.call_args_list[0].args[0]
        second_args = popen.call_args_list[1].args[0]
        self.assertIn("--new-window", first_args)
        self.assertIn("--new-tab", second_args)
        self.assertEqual(first_args[-1], "https://genius.com/first")
        self.assertEqual(second_args[-1], "https://genius.com/second")

    @patch("spotify_genius.core.browser.opener.platform.system", return_value="Windows")
    @patch("spotify_genius.core.browser.opener.windows.select_browser", return_value=None)
    @patch("spotify_genius.core.browser.opener.webbrowser.open")
    def test_windows_opener_falls_back_to_webbrowser_when_no_supported_browser_is_found(
        self,
        webbrowser_open,
        _select_browser,
        _system,
    ):
        DedicatedBrowserOpener().open("https://genius.com/fallback")

        webbrowser_open.assert_called_once_with("https://genius.com/fallback")

    def test_desktop_exec_args_drop_url_placeholders(self):
        self.assertEqual(
            _clean_desktop_exec_args(
                [
                    "/usr/bin/flatpak",
                    "run",
                    "--branch=stable",
                    "--file-forwarding",
                    "com.google.Chrome",
                    "@@u",
                    "%U",
                    "@@",
                ]
            ),
            (
                "/usr/bin/flatpak",
                "run",
                "--branch=stable",
                "com.google.Chrome",
            ),
        )

    @patch("spotify_genius.core.browser.linux.shutil.which", return_value="/usr/bin/flatpak")
    @patch("spotify_genius.core.browser.linux.subprocess.run")
    def test_flatpak_browser_can_be_resolved_from_desktop_id(self, run, _which):
        run.return_value.returncode = 0

        browser = _browser_from_flatpak_app_id("com.google.Chrome.desktop")

        self.assertEqual(
            browser,
            BrowserSpec(("/usr/bin/flatpak", "run", "com.google.Chrome"), "chromium"),
        )

    @patch.dict("spotify_genius.core.browser.windows.os.environ", {"LOCALAPPDATA": r"C:\Users\Andre\AppData\Local"})
    def test_windows_profile_dir_uses_local_app_data(self):
        browser = BrowserSpec((r"C:\Program Files\Google\Chrome\Application\chrome.exe",), "chromium")

        self.assertEqual(
            _windows_profile_dir(browser),
            Path(r"C:\Users\Andre\AppData\Local") / "SpotifyGenius" / "BrowserProfile" / "chrome.exe",
        )

    @patch("spotify_genius.core.browser.common.platform.system", return_value="Windows")
    @patch("spotify_genius.core.browser.common.shutil.which", return_value=None)
    @patch.dict(
        "spotify_genius.core.browser.common.os.environ",
        {
            "SPOTIFY_GENIUS_BROWSER": r'"C:\Program Files\Google\Chrome\Application\chrome.exe" --disable-extensions'
        },
    )
    def test_windows_env_browser_command_supports_quoted_paths(self, _which, _system):
        self.assertEqual(
            _split_command(r'"C:\Program Files\Google\Chrome\Application\chrome.exe" --disable-extensions'),
            [
                r'"C:\Program Files\Google\Chrome\Application\chrome.exe"',
                "--disable-extensions",
            ],
        )
        self.assertEqual(
            _browser_from_env(),
            BrowserSpec(
                (r"C:\Program Files\Google\Chrome\Application\chrome.exe",),
                "chromium",
                ("--disable-extensions",),
            ),
        )

    @patch("spotify_genius.core.browser.windows._default_windows_browser", return_value="ChromeHTML")
    @patch("spotify_genius.core.browser.windows._find_windows_executable")
    def test_windows_browser_selection_prefers_default_browser(self, find_executable, _default_browser):
        def fake_find(executable_name):
            return {
                "chrome.exe": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "msedge.exe": r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            }.get(executable_name)

        find_executable.side_effect = fake_find

        self.assertEqual(
            _select_windows_browser(),
            BrowserSpec((r"C:\Program Files\Google\Chrome\Application\chrome.exe",), "chromium"),
        )


if __name__ == "__main__":
    unittest.main()
