import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from custom_components.plex_assistant.players import _build, _extract_id, play_external
from custom_components.plex_assistant.responses import get_responses
from custom_components.plex_assistant.router import Route


class FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


def fake_hass():
    return SimpleNamespace(services=FakeServices())


def load_services_config():
    path = Path(__file__).parent.parent / "custom_components/plex_assistant/services_config.json"
    config = json.loads(path.read_text())
    config.pop("_comment", None)
    return config


def make_data():
    return SimpleNamespace(responses=get_responses("sv"), services_config=load_services_config())


def netflix_route():
    config = load_services_config()
    return Route(
        source="netflix",
        title="Dune",
        service=config["netflix"],
        url="https://www.netflix.com/title/81161626",
    )


def test_extract_id():
    assert _extract_id("https://www.netflix.com/title/81161626") == "81161626"
    assert _extract_id("https://www.netflix.com/title/81161626?s=1") == "81161626"


def test_build_templates():
    assert _build("{url}", "https://x/y/1") == "https://x/y/1"
    assert _build("m={url}", "https://x/y/1") == "m=https://x/y/1"
    assert _build("nflx://{id}", "https://x/title/42") == "nflx://42"
    assert _build(None, "https://x") is None
    assert _build("{url}", None) is None


def test_webos_deep_link():
    hass = fake_hass()
    device = {"entity_id": "media_player.lg_c9", "device_type": "webos", "device_id": "d1"}
    message = asyncio.run(play_external(hass, make_data(), netflix_route(), device, "LG C9"))
    domain, service, data = hass.services.calls[0]
    assert (domain, service) == ("webostv", "command")
    assert data["command"] == "system.launcher/launch"
    assert data["payload"]["id"] == "netflix"
    assert data["payload"]["contentId"] == "m=https://www.netflix.com/title/81161626"
    assert "Netflix" in message and "Dune" in message


def test_apple_tv_deep_link():
    hass = fake_hass()
    device = {"entity_id": "media_player.apple_tv", "device_type": "apple_tv", "device_id": "d2"}
    asyncio.run(play_external(hass, make_data(), netflix_route(), device, "Apple TV"))
    domain, service, data = hass.services.calls[0]
    assert (domain, service) == ("media_player", "play_media")
    assert data["media_content_type"] == "app"
    assert data["media_content_id"] == "https://www.netflix.com/title/81161626"


def test_webos_app_launch_without_content_template():
    # Max has no webOS contentId template -> app launch only + "opening app" response
    hass = fake_hass()
    config = load_services_config()
    route = Route(source="max", title="Succession", service=config["max"], url="https://play.max.com/x/1")
    device = {"entity_id": "media_player.lg_c9", "device_type": "webos", "device_id": "d1"}
    message = asyncio.run(play_external(hass, make_data(), route, device, "LG C9"))
    _, _, data = hass.services.calls[0]
    assert "contentId" not in data["payload"]
    assert "Öppnar appen" in message


def plex_app_route():
    config = load_services_config()
    return Route(source="plex", title="Dune", service=config["plex"], url=None)


def test_plex_app_launch_on_webos():
    hass = fake_hass()
    device = {"entity_id": "media_player.lg_c9", "device_type": "webos", "device_id": "d1"}
    asyncio.run(play_external(hass, make_data(), plex_app_route(), device, "LG C9"))
    domain, service, data = hass.services.calls[0]
    assert (domain, service) == ("webostv", "command")
    assert data["payload"]["id"] == "cdp-30"
    assert "contentId" not in data["payload"]


def test_plex_app_launch_on_apple_tv():
    hass = fake_hass()
    device = {"entity_id": "media_player.apple_tv", "device_type": "apple_tv", "device_id": "d2"}
    asyncio.run(play_external(hass, make_data(), plex_app_route(), device, "Apple TV"))
    domain, service, data = hass.services.calls[0]
    assert (domain, service) == ("media_player", "play_media")
    assert data["media_content_type"] == "app"
    assert data["media_content_id"] == "com.plexapp.plex"


def test_plain_cast_device_cannot_open_apps():
    hass = fake_hass()

    def no_sibling(*args, **kwargs):
        return None

    import custom_components.plex_assistant.players as players_module

    original = players_module.find_entity_for_device
    players_module.find_entity_for_device = no_sibling
    try:
        device = {"entity_id": "media_player.chromecast", "device_type": "cast", "device_id": "d3"}
        message = asyncio.run(play_external(hass, make_data(), netflix_route(), device, "Chromecast"))
    finally:
        players_module.find_entity_for_device = original
    assert hass.services.calls == []
    assert "kan inte öppna" in message
