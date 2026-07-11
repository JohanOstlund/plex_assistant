"""Lookup of external streaming availability via Plex Discover.

The metadata.provider.plex.tv API is unofficial and undocumented, so parsing here is
deliberately defensive: we walk the JSON for recognizable shapes instead of assuming
an exact schema, and log raw payloads at debug level. If Plex changes the API, set
`logger: custom_components.plex_assistant: debug` and open an issue with the output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from ..const import _LOGGER

BASE_URL = "https://metadata.provider.plex.tv"
SEARCH_MATCH_THRESHOLD = 70


@dataclass
class Availability:
    platform: str
    url: str | None
    raw: dict = field(default_factory=dict)


@dataclass
class DiscoverResult:
    title: str
    year: int | None
    media_type: str | None
    rating_key: str
    availabilities: list[Availability] = field(default_factory=list)


class PlexDiscover:
    def __init__(self, session, token: str, region: str = "SE"):
        self._session = session
        self._token = token
        self._region = region

    @property
    def _headers(self):
        return {"X-Plex-Token": self._token, "Accept": "application/json"}

    async def _get(self, path: str, params: dict) -> dict | None:
        try:
            async with self._session.get(
                f"{BASE_URL}{path}", params=params, headers=self._headers, timeout=10
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Plex Discover returned %s for %s", resp.status, path)
                    return None
                return await resp.json()
        except Exception as error:  # noqa: BLE001
            _LOGGER.warning("Plex Discover request failed: %s", error)
            return None

    async def find(self, title: str) -> DiscoverResult | None:
        """Search Discover for a title and return it with its streaming availabilities."""
        data = await self._get(
            "/library/search",
            {
                "query": title,
                "limit": 10,
                "searchTypes": "movies,tv",
                "includeMetadata": 1,
                "searchProviders": "discover",
            },
        )
        if not data:
            return None
        _LOGGER.debug("Discover search raw: %s", data)

        candidates = _extract_metadata_items(data)
        best = _best_match(title, candidates)
        if not best:
            _LOGGER.debug("Discover: no match for '%s'", title)
            return None

        result = DiscoverResult(
            title=best.get("title", title),
            year=best.get("year"),
            media_type=best.get("type"),
            rating_key=str(best.get("ratingKey", "")),
        )
        if not result.rating_key:
            return None

        avail_data = await self._get(
            f"/library/metadata/{result.rating_key}",
            {"includeAvailabilities": 1, "country": self._region},
        )
        if not avail_data:
            return result
        _LOGGER.debug("Discover availabilities raw: %s", avail_data)

        result.availabilities = _extract_availabilities(avail_data)
        _LOGGER.debug(
            "Discover: '%s' (%s) available on: %s",
            result.title,
            result.year,
            [a.platform for a in result.availabilities],
        )
        return result


def _extract_metadata_items(data) -> list[dict]:
    """Collect anything that looks like a movie/show metadata dict from the response."""
    items = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("title") and node.get("ratingKey") and node.get("type") in ("movie", "show"):
                items.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return items


def _best_match(title: str, candidates: list[dict]) -> dict | None:
    best, best_score = None, 0
    for item in candidates:
        score = fuzz.WRatio(title.lower(), str(item.get("title", "")).lower())
        if score > best_score:
            best, best_score = item, score
    return best if best_score >= SEARCH_MATCH_THRESHOLD else None


def _extract_availabilities(data) -> list[Availability]:
    """Collect anything that looks like a streaming availability entry."""
    found = []
    seen = set()

    def walk(node):
        if isinstance(node, dict):
            platform = node.get("platform") or node.get("source")
            url = node.get("url") or node.get("uri")
            if platform and isinstance(platform, str) and (url is None or isinstance(url, str)):
                key = (platform, url)
                if url and key not in seen:
                    seen.add(key)
                    found.append(Availability(platform=platform.lower(), url=url, raw=node))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return found
