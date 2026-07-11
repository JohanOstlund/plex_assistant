from types import SimpleNamespace

from custom_components.plex_assistant.localize import translations
from custom_components.plex_assistant.process_speech import ProcessSpeech

SERVICES = {
    "netflix": {"name": "Netflix", "aliases": ["netflix"]},
    "max": {"name": "Max", "aliases": ["max", "hbo", "hbo max"]},
    "disneyplus": {"name": "Disney+", "aliases": ["disney", "disney plus", "disney+"]},
}


def fake_pa():
    titles = ["Dune", "The Office", "Severance"]
    return SimpleNamespace(
        device_names=["Vardagsrummet", "LG C9"],
        devices={},
        media={
            "all_titles": titles,
            "movie_titles": titles,
            "show_titles": [],
            "artist_titles": [],
            "album_titles": [],
            "track_titles": [],
            "playlist_titles": [],
        },
    )


def process(command, lang="sv"):
    return ProcessSpeech(fake_pa(), translations[lang], command, "Vardagsrummet", SERVICES).results


def test_swedish_explicit_netflix():
    result = process("spela dune på netflix på vardagsrummet")
    assert result["service"] == "netflix"
    assert "netflix" not in result["media"]
    assert "dune" in result["media"]


def test_swedish_explicit_plex():
    result = process("spela dune på plex på vardagsrummet")
    assert result["service"] == "plex"
    assert "plex" not in result["media"]


def test_swedish_no_service():
    result = process("spela dune på vardagsrummet")
    assert result["service"] is None
    assert "dune" in result["media"]


def test_longest_alias_wins():
    result = process("spela succession på hbo max på vardagsrummet")
    assert result["service"] == "max"
    assert "hbo" not in result["media"]


def test_device_still_detected_after_service_removal():
    result = process("spela dune på netflix på lg c9")
    assert result["service"] == "netflix"
    assert result["device"] and "c9" in result["device"].lower()


def test_english_explicit_service():
    result = process("play dune on disney plus on the vardagsrummet", lang="en")
    assert result["service"] == "disneyplus"
