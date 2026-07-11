"""Lookup of external streaming availability via Plex Discover.

The discover.provider.plex.tv API is unofficial and undocumented, so parsing here is
deliberately defensive: we walk the JSON for recognizable shapes instead of assuming
an exact schema, and log raw payloads at debug level. If Plex changes the API, set
`logger: custom_components.plex_assistant: debug` and open an issue with the output.

Endpoints (verified against the live API 2026-07-11):
- GET /library/search?query=...&searchTypes=movies,tv  -> SearchResults[].SearchResult[].Metadata
- GET /library/metadata/{ratingKey}/availabilities?country=SE
  -> MediaContainer.Availability[]: platform, platformUrl, offerType,
     platformInfo.{web,androidTV,iOS,...}.url
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from rapidfuzz import fuzz

from ..const import _LOGGER

BASE_URL = "https://discover.provider.plex.tv"
SEARCH_MATCH_THRESHOLD = 70

# Offers that require paying per title are not "available on the service"
EXCLUDED_OFFER_TYPES = {"rent", "rental", "buy", "purchase", "tvod"}


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

    async def find_all(self, title: str) -> list[DiscoverResult]:
        """Search Discover and return near-equal candidates, best match first,
        each with its streaming availabilities. The best fuzzy match can be e.g.
        an unreleased remake, so the caller picks the candidate that is actually
        available where the user asked for it."""
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
            return []
        _LOGGER.debug("Discover search raw: %s", data)

        ranked = _rank_matches(title, _extract_metadata_items(data))
        if not ranked:
            _LOGGER.debug("Discover: no match for '%s'", title)
            return []

        top_score = ranked[0][0]
        candidates = [item for score, item in ranked[:4] if score >= top_score - 15 and item.get("ratingKey")]

        async def fetch(item) -> DiscoverResult:
            result = DiscoverResult(
                title=item.get("title", title),
                year=item.get("year"),
                media_type=item.get("type"),
                rating_key=str(item["ratingKey"]),
            )
            avail_data = await self._get(
                f"/library/metadata/{result.rating_key}/availabilities",
                {"country": self._region},
            )
            if avail_data:
                result.availabilities = _extract_availabilities(avail_data)
            return result

        results = list(await asyncio.gather(*(fetch(item) for item in candidates)))
        for result in results:
            _LOGGER.debug(
                "Discover: '%s' (%s) available on: %s",
                result.title,
                result.year,
                [a.platform for a in result.availabilities],
            )
        return results

    async def find(self, title: str) -> DiscoverResult | None:
        """First candidate that is streamable somewhere, else the best match."""
        results = await self.find_all(title)
        for result in results:
            if result.availabilities:
                return result
        return results[0] if results else None


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


def _rank_matches(title: str, candidates: list[dict]) -> list[tuple[float, dict]]:
    """Candidates scoring above the threshold, best first, deduped on ratingKey."""
    ranked = []
    seen = set()
    for item in candidates:
        key = item.get("ratingKey")
        if key in seen:
            continue
        seen.add(key)
        score = fuzz.WRatio(title.lower(), str(item.get("title", "")).lower())
        if score >= SEARCH_MATCH_THRESHOLD:
            ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked


def _best_match(title: str, candidates: list[dict]) -> dict | None:
    ranked = _rank_matches(title, candidates)
    return ranked[0][1] if ranked else None


def _unwrap_redirect(url: str) -> str:
    """Affiliate wrappers (pxf.io, bn5x.net, ...) hide the real title URL in ?u=."""
    try:
        query = parse_qs(urlsplit(url).query)
    except ValueError:
        return url
    for key in ("u", "url"):
        for candidate in query.get(key, []):
            if candidate.startswith(("http://", "https://")):
                return candidate
    return url


def _extract_availabilities(data) -> list[Availability]:
    """Collect anything that looks like a streaming availability entry."""
    found = []
    seen = set()

    def walk(node):
        if isinstance(node, dict):
            platform = node.get("platform")
            url = node.get("url") or node.get("uri") or node.get("platformUrl")
            offer_type = node.get("offerType")
            if (
                platform
                and isinstance(platform, str)
                and isinstance(url, str)
                and str(offer_type or "").lower() not in EXCLUDED_OFFER_TYPES
            ):
                url = _unwrap_redirect(url)
                key = (platform, url)
                if key not in seen:
                    seen.add(key)
                    found.append(Availability(platform=platform.lower(), url=url, raw=node))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return found
