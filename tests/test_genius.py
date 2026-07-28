import unittest
from pathlib import Path
from unittest.mock import patch

from spotify_genius.core.browser import (
    BrowserSpec,
    DedicatedBrowserOpener,
    _build_browser_args,
    _browser_from_flatpak_app_id,
    _clean_desktop_exec_args,
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

    @patch("spotify_genius.core.browser.platform.system", return_value="Linux")
    @patch(
        "spotify_genius.core.browser._linux_profile_dir",
        return_value=Path("/tmp/spotify-genius-test-profile"),
    )
    @patch(
        "spotify_genius.core.browser._select_linux_browser",
        return_value=BrowserSpec(("/usr/bin/google-chrome",), "chromium"),
    )
    @patch("spotify_genius.core.browser._open_chromium_tab", return_value=True)
    @patch("spotify_genius.core.browser._find_available_port", return_value=9222)
    @patch("spotify_genius.core.browser.subprocess.Popen")
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

    @patch("spotify_genius.core.browser.platform.system", return_value="Linux")
    @patch(
        "spotify_genius.core.browser._linux_profile_dir",
        return_value=Path("/tmp/spotify-genius-test-profile"),
    )
    @patch(
        "spotify_genius.core.browser._select_linux_browser",
        return_value=BrowserSpec(("/usr/bin/firefox",), "firefox"),
    )
    @patch("spotify_genius.core.browser.subprocess.Popen")
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

    @patch("spotify_genius.core.browser.platform.system", return_value="Linux")
    @patch("spotify_genius.core.browser._select_linux_browser", return_value=None)
    @patch("spotify_genius.core.browser.webbrowser.open")
    def test_linux_opener_falls_back_to_webbrowser_when_no_supported_browser_is_found(
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

    @patch("spotify_genius.core.browser.shutil.which", return_value="/usr/bin/flatpak")
    @patch("spotify_genius.core.browser.subprocess.run")
    def test_flatpak_browser_can_be_resolved_from_desktop_id(self, run, _which):
        run.return_value.returncode = 0

        browser = _browser_from_flatpak_app_id("com.google.Chrome.desktop")

        self.assertEqual(
            browser,
            BrowserSpec(("/usr/bin/flatpak", "run", "com.google.Chrome"), "chromium"),
        )


if __name__ == "__main__":
    unittest.main()
