import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import unescape
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from unidecode import unidecode

from spotify_genius.core.browser import open_url

GENIUS_SEARCH_URL = "https://genius.com/api/search/song"
GENIUS_SEARCH_PAGE_URL = "https://genius.com/search"
GENIUS_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "spotify-genius/0.1.6",
    "X-Requested-With": "XMLHttpRequest",
}
VERSION_WORDS = (
    "acoustic",
    "clean",
    "demo",
    "edit",
    "explicit",
    "instrumental",
    "karaoke",
    "live",
    "mix",
    "radio",
    "remaster",
    "remastered",
    "version",
)


@dataclass(frozen=True)
class GeniusCandidate:
    url: str
    score: float


def remove_features(title_song: str) -> str:
    cleaned = re.sub(
        r"\s*[\[(](feat|ft|with)\.?\s+[^)\]]*[\])]",
        "",
        title_song,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def strip_version_tags(title_song: str) -> str:
    title_song = re.sub(
        r"\s*[\[(][^)\]]*(remaster|live|acoustic|edit|version|mix)[^)\]]*[\])]",
        "",
        title_song,
        flags=re.IGNORECASE,
    )
    title_song = re.sub(
        r"\s*[-:]\s*(remaster(?:ed)?(?:\s+\d{4})?|live|acoustic|radio edit|edit|version|mix)$",
        "",
        title_song,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", title_song).strip()


def normalize_text(text: str) -> str:
    text = unescape(text or "")
    text = text.replace("&", " and ")
    text = unidecode(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_text(text: str) -> str:
    normalized = normalize_text(text)
    if normalized:
        return normalized
    return unescape(text or "").strip().lower()


def title_variants(title: str) -> list[str]:
    variants = []
    for candidate in (
        title.strip(),
        remove_features(title),
        strip_version_tags(remove_features(title)),
    ):
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def artist_variants(artist: str) -> list[str]:
    variants = []
    raw_variants = (
        artist.strip(),
        re.split(r"\s*,\s*|\s*&\s*|\s+x\s+|\s+and\s+", artist, maxsplit=1)[0].strip(),
    )
    for candidate in raw_variants:
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def generate_genius_slug(artist: str, title: str) -> str:
    title = strip_version_tags(remove_features(title))
    text = f"{artist} {title}"
    text = text.replace("'", "")
    text = text.replace('"', "")
    text = text.replace("&", "and")
    text = unidecode(text)
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-") + "-lyrics"


def build_search_queries(artist: str, title: str) -> list[str]:
    queries = []
    for artist_name in artist_variants(artist):
        for title_name in title_variants(title):
            for query in (
                f"{artist_name} {title_name}",
                f"{title_name} {artist_name}",
            ):
                query = query.strip()
                if query and query not in queries:
                    queries.append(query)
    return queries


def fetch_search_hits(query: str) -> list[dict]:
    params = urlencode({"q": query, "page": 1, "per_page": 10})
    request = Request(f"{GENIUS_SEARCH_URL}?{params}", headers=GENIUS_HEADERS)
    with urlopen(request, timeout=5) as response:
        payload = json.load(response)

    sections = payload.get("response", {}).get("sections", [])
    hits = []
    for section in sections:
        section_hits = section.get("hits", [])
        if section.get("type") == "song":
            hits.extend(section_hits)
    if hits:
        return hits

    for section in sections:
        hits.extend(section.get("hits", []))
    return hits


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def _token_overlap(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def _version_penalty(expected_title: str, result_title: str) -> float:
    penalty = 0.0
    for word in VERSION_WORDS:
        expected_has = word in expected_title
        result_has = word in result_title
        if result_has and not expected_has:
            penalty += 0.25
    return penalty


def score_hit(artist: str, title: str, hit: dict) -> float:
    result = hit.get("result", {})
    result_title = match_text(result.get("title", ""))
    result_full_title = match_text(result.get("title_with_featured", ""))
    result_artist = normalize_text(result.get("primary_artist", {}).get("name", ""))

    expected_title = match_text(strip_version_tags(remove_features(title)))
    expected_artist_names = [normalize_text(name) for name in artist_variants(artist)]
    result_title_candidates = [candidate for candidate in (result_title, result_full_title) if candidate]

    if not result_title_candidates:
        return 0.0

    title_score = max(
        _similarity(expected_title, candidate)
        for candidate in result_title_candidates
    )
    title_overlap = max(
        _token_overlap(expected_title, candidate)
        for candidate in result_title_candidates
    )
    artist_score = max(_similarity(candidate, result_artist) for candidate in expected_artist_names)
    artist_overlap = max(_token_overlap(candidate, result_artist) for candidate in expected_artist_names)

    score = (title_score * 0.65) + (title_overlap * 0.15) + (artist_score * 0.15) + (artist_overlap * 0.05)
    score -= _version_penalty(expected_title, result_title)

    if artist_score < 0.55 and artist_overlap < 0.5:
        score -= 0.45

    if result_title == expected_title:
        score += 0.25
    if result_artist in expected_artist_names:
        score += 0.15

    return score


def select_best_candidate(artist: str, title: str, hits: Iterable[dict]) -> GeniusCandidate | None:
    best_by_url: dict[str, GeniusCandidate] = {}

    for hit in hits:
        result = hit.get("result", {})
        url = result.get("url")
        if not url:
            continue

        candidate = GeniusCandidate(url=url, score=score_hit(artist, title, hit))
        current = best_by_url.get(url)
        if current is None or candidate.score > current.score:
            best_by_url[url] = candidate

    if not best_by_url:
        return None

    ranked = sorted(best_by_url.values(), key=lambda candidate: candidate.score, reverse=True)
    best = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None

    if best.score < 0.78:
        return None
    if runner_up and best.score - runner_up.score < 0.08:
        return None
    return best


def resolve_genius_url(artist: str, title: str) -> tuple[str, str]:
    queries = build_search_queries(artist, title)
    all_hits = []
    had_network_error = False

    for query in queries:
        try:
            all_hits.extend(fetch_search_hits(query))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            had_network_error = True

    best = select_best_candidate(artist, title, all_hits)
    if best is not None:
        return best.url, "matched"

    if queries and not had_network_error:
        search_url = f"{GENIUS_SEARCH_PAGE_URL}?{urlencode({'q': queries[0]})}"
        return search_url, "search"

    slug_url = f"https://genius.com/{generate_genius_slug(artist, title)}"
    return slug_url, "slug"


def open_genius(artist: str, title: str):
    url, strategy = resolve_genius_url(artist, title)
    if strategy == "matched":
        print(f"Opening matched Genius page: {url}")
    elif strategy == "search":
        print(f"Opening Genius search results for manual confirmation: {url}")
    else:
        print(f"Opening fallback Genius URL: {url}")
    open_url(url)
