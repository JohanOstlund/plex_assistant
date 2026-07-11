from custom_components.plex_assistant.handler import _plex_capable_in_area


def devices():
    return {
        "Allrum": {"entity_id": "media_player.allrum_2", "device_type": "apple_tv", "area_id": "allrum"},
        "Plex SHIELD": {"entity_id": "media_player.plex_shield", "device_type": "plex", "area_id": "allrum"},
        "SHIELD": {"entity_id": "media_player.shield", "device_type": "cast", "area_id": "allrum"},
        "Kök": {"entity_id": "media_player.kok", "device_type": "cast", "area_id": "kok"},
    }


class FakePa:
    def __init__(self, devs):
        self.devices = devs


def test_plex_prefers_cast_in_same_area():
    pa = FakePa(devices())
    apple_tv = pa.devices["Allrum"]
    info, name = _plex_capable_in_area(pa, apple_tv)
    # Chromecast (cast) beats the Plex client when both are in the room
    assert name == "SHIELD"
    assert info["device_type"] == "cast"


def test_plex_falls_back_to_plex_client_when_no_cast():
    devs = devices()
    del devs["SHIELD"]
    info, name = _plex_capable_in_area(FakePa(devs), devs["Allrum"])
    assert name == "Plex SHIELD"
    assert info["device_type"] == "plex"


def test_no_plex_target_in_other_area():
    devs = devices()
    devs["Allrum"]["area_id"] = "sovrum"  # a room with no plex-capable device
    del devs["SHIELD"]
    del devs["Plex SHIELD"]
    info, name = _plex_capable_in_area(FakePa(devs), devs["Allrum"])
    assert info is None


def test_no_area_means_no_redirect():
    devs = devices()
    devs["Allrum"]["area_id"] = None
    info, name = _plex_capable_in_area(FakePa(devs), devs["Allrum"])
    assert info is None
