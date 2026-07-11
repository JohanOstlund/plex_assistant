from custom_components.plex_assistant.sources.plex_discover import (
    _best_match,
    _extract_availabilities,
    _extract_metadata_items,
)

SEARCH_RESPONSE = {
    "MediaContainer": {
        "SearchResults": [
            {
                "id": "external",
                "SearchResult": [
                    {
                        "score": 0.95,
                        "Metadata": {
                            "title": "Dune",
                            "year": 2021,
                            "type": "movie",
                            "ratingKey": "5d776b9a594b2b001e6ea5f0",
                            "guid": "plex://movie/5d776b9a594b2b001e6ea5f0",
                        },
                    },
                    {
                        "score": 0.55,
                        "Metadata": {
                            "title": "Dune: Part Two",
                            "year": 2024,
                            "type": "movie",
                            "ratingKey": "aaa",
                        },
                    },
                ],
            }
        ]
    }
}

AVAILABILITY_RESPONSE = {
    "MediaContainer": {
        "Metadata": [
            {
                "title": "Dune",
                "Availabilities": [
                    {
                        "platform": "Netflix",
                        "url": "https://www.netflix.com/title/81161626",
                        "offerType": "subscription",
                    },
                    {
                        "platform": "hbo-max",
                        "url": "https://play.max.com/movie/abc",
                        "offerType": "subscription",
                    },
                    {"platform": "broken-no-url"},
                ],
            }
        ]
    }
}


def test_extract_metadata_items_finds_movies():
    items = _extract_metadata_items(SEARCH_RESPONSE)
    titles = [i["title"] for i in items]
    assert "Dune" in titles and "Dune: Part Two" in titles


def test_best_match_picks_right_title():
    items = _extract_metadata_items(SEARCH_RESPONSE)
    best = _best_match("dune", items)
    assert best["ratingKey"] == "5d776b9a594b2b001e6ea5f0"


def test_best_match_rejects_garbage():
    items = _extract_metadata_items(SEARCH_RESPONSE)
    assert _best_match("helt annan film", items) is None


def test_extract_availabilities():
    found = _extract_availabilities(AVAILABILITY_RESPONSE)
    platforms = {a.platform: a.url for a in found}
    assert platforms["netflix"] == "https://www.netflix.com/title/81161626"
    assert platforms["hbo-max"] == "https://play.max.com/movie/abc"
    assert "broken-no-url" not in platforms
