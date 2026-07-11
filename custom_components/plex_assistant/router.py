"""Source routing: decide whether a command plays from local Plex or an external service.

Policy, in order:
1. A service named in the command ("på netflix", "på plex") always wins.
2. Otherwise the configured source priority list decides; the first source that
   actually has the title is used (default priority: just "plex").
3. If nothing in the priority list has it, fall back to a weaker local match,
   then to any known external availability.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import _LOGGER, LOCAL_MATCH_THRESHOLD
from .sources.plex_discover import DiscoverResult


@dataclass
class Route:
    source: str  # "plex" or a service key from services_config
    title: str | None = None
    service: dict | None = None  # services_config entry for external routes
    url: str | None = None  # availability web URL for external routes


class RouteError(Exception):
    """Routing failed; str(error) is a response key in responses.py."""

    def __init__(self, response_key: str, **kwargs):
        super().__init__(response_key)
        self.response_key = response_key
        self.kwargs = kwargs


def _availability_for(service_key: str, services_config: dict, discover_result: DiscoverResult | None):
    if not discover_result:
        return None
    service = services_config.get(service_key)
    if not service:
        return None
    match_strings = [m.lower() for m in service.get("match", [service_key])]
    for availability in discover_result.availabilities:
        if any(m == availability.platform or m in availability.platform for m in match_strings):
            return availability
    return None


def _first_with(service_key: str, services_config: dict, results: list[DiscoverResult]):
    """First candidate title that is available on the given service."""
    for result in results:
        availability = _availability_for(service_key, services_config, result)
        if availability:
            return result, availability
    return None, None


async def async_route(hass, data, command, local_result) -> Route:
    """Decide playback source. local_result is find_media's [media, library, score]."""
    media_name = command["media"] if isinstance(command["media"], str) else None
    local_score = local_result[2]
    local_ok = local_score >= LOCAL_MATCH_THRESHOLD
    forced = command.get("service")
    external_services = [s for s in data.source_priority if s != "plex"]

    discover_results: list[DiscoverResult] = []
    discover_fetched = False

    async def get_discover() -> list[DiscoverResult]:
        nonlocal discover_results, discover_fetched
        if not discover_fetched:
            discover_fetched = True
            if data.discover and media_name:
                discover_results = await data.discover.find_all(media_name)
        return discover_results

    if forced == "plex":
        _LOGGER.debug("Route: forced to local Plex")
        return Route(source="plex")

    if forced:
        service = data.services_config.get(forced)
        result, availability = _first_with(forced, data.services_config, await get_discover())
        if service and availability:
            _LOGGER.debug("Route: forced to %s (%s)", forced, availability.url)
            return Route(source=forced, title=result.title, service=service, url=availability.url)
        raise RouteError(
            "not_on_service",
            media=(discover_results[0].title if discover_results else media_name) or "?",
            service=(service or {}).get("name", forced),
        )

    for source in data.source_priority:
        if source == "plex":
            if local_ok:
                _LOGGER.debug("Route: local Plex (score %s)", local_score)
                return Route(source="plex")
        elif source in data.services_config:
            result, availability = _first_with(source, data.services_config, await get_discover())
            if availability:
                _LOGGER.debug("Route: %s via priority (%s)", source, availability.url)
                return Route(
                    source=source,
                    title=result.title,
                    service=data.services_config[source],
                    url=availability.url,
                )

    # Nothing in the priority list had it: weaker local match beats giving up
    if local_score >= 60:
        _LOGGER.debug("Route: weak local match fallback (score %s)", local_score)
        return Route(source="plex")

    # Last resort: any configured external service that has it, in config order
    results = await get_discover()
    if results:
        for source in external_services or data.services_config.keys():
            result, availability = _first_with(source, data.services_config, results)
            if availability:
                _LOGGER.debug("Route: last-resort external %s (%s)", source, availability.url)
                return Route(
                    source=source,
                    title=result.title,
                    service=data.services_config[source],
                    url=availability.url,
                )

    raise RouteError("not_found", media=media_name or "?")
