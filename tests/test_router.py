import asyncio
from types import SimpleNamespace

import pytest

from custom_components.plex_assistant.router import Route, RouteError, async_route
from custom_components.plex_assistant.sources.plex_discover import Availability, DiscoverResult

SERVICES = {
    "netflix": {"name": "Netflix", "aliases": ["netflix"], "match": ["netflix"]},
    "max": {"name": "Max", "aliases": ["max", "hbo max"], "match": ["max", "hbo-max"]},
}


class FakeDiscover:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def find(self, title):
        self.calls += 1
        return self.result


def make_data(priority, discover_result=None):
    return SimpleNamespace(
        source_priority=priority,
        services_config=SERVICES,
        discover=FakeDiscover(discover_result),
    )


def dune_on_netflix():
    return DiscoverResult(
        title="Dune",
        year=2021,
        media_type="movie",
        rating_key="abc123",
        availabilities=[Availability(platform="netflix", url="https://www.netflix.com/title/81161626")],
    )


def command(media="dune", service=None):
    return {"media": media, "service": service}


def route(data, cmd, local_score):
    return asyncio.run(async_route(None, data, cmd, ["Dune", "movie", local_score]))


def test_forced_plex_wins_even_when_external_exists():
    data = make_data(["netflix", "plex"], dune_on_netflix())
    result = route(data, command(service="plex"), local_score=100)
    assert result.source == "plex"
    assert data.discover.calls == 0


def test_forced_service_overrides_local_hit():
    data = make_data(["plex"], dune_on_netflix())
    result = route(data, command(service="netflix"), local_score=100)
    assert result.source == "netflix"
    assert result.url == "https://www.netflix.com/title/81161626"


def test_forced_service_not_available_raises():
    data = make_data(["plex"], dune_on_netflix())
    with pytest.raises(RouteError) as err:
        route(data, command(service="max"), local_score=0)
    assert err.value.response_key == "not_on_service"


def test_plex_first_local_hit_skips_discover():
    data = make_data(["plex", "netflix"], dune_on_netflix())
    result = route(data, command(), local_score=90)
    assert result.source == "plex"
    assert data.discover.calls == 0


def test_priority_service_above_plex_wins_when_available():
    data = make_data(["netflix", "plex"], dune_on_netflix())
    result = route(data, command(), local_score=90)
    assert result.source == "netflix"


def test_external_fallback_when_not_local():
    data = make_data(["plex", "netflix"], dune_on_netflix())
    result = route(data, command(), local_score=30)
    assert result.source == "netflix"


def test_weak_local_match_beats_nothing():
    data = make_data(["plex"], None)
    result = route(data, command(), local_score=65)
    assert result.source == "plex"


def test_nothing_found_raises():
    data = make_data(["plex", "netflix"], None)
    with pytest.raises(RouteError) as err:
        route(data, command(), local_score=10)
    assert err.value.response_key == "not_found"


def test_last_resort_any_configured_service():
    # priority only has plex, but the title exists on netflix -> play it there
    data = make_data(["plex"], dune_on_netflix())
    result = route(data, command(), local_score=10)
    assert result.source == "netflix"
