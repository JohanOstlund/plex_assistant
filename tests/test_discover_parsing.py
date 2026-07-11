import asyncio

from custom_components.plex_assistant.sources.plex_discover import (
    PlexDiscover,
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

# Shape verified against the live API 2026-07-11
AVAILABILITY_RESPONSE = {
    "MediaContainer": {
        "identifier": "tv.plex.provider.discover",
        "size": 4,
        "Availability": [
            {
                "country": "SE",
                "offerType": "subscription",
                "platform": "netflix",
                "platformUrl": "https://www.netflix.com/title/81161626",
                "platformInfo": {"web": {"url": "https://www.netflix.com/title/81161626"}},
                "title": "Netflix",
            },
            {
                "country": "SE",
                "offerType": "subscription",
                "platform": "max",
                "platformUrl": "https://play.max.com/movie/abc",
                "title": "HBO Max",
            },
            {
                "country": "SE",
                "offerType": "rental",
                "platform": "apple-itunes",
                "platformUrl": "https://tv.apple.com/movie/xyz",
                "title": "Apple TV",
            },
            {"platform": "broken-no-url"},
        ],
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
    assert platforms["max"] == "https://play.max.com/movie/abc"
    assert "broken-no-url" not in platforms


def test_extract_availabilities_skips_rent_and_buy():
    found = _extract_availabilities(AVAILABILITY_RESPONSE)
    assert "apple-itunes" not in {a.platform for a in found}


def test_find_falls_through_to_candidate_with_availabilities():
    # Best fuzzy match is an unreleased title with no availabilities (like the 2026
    # "Avatar Aang" movie); a near-equal candidate that is streamable should win.
    search = {
        "MediaContainer": {
            "SearchResults": [
                {
                    "SearchResult": [
                        {"Metadata": {"title": "Avatar Aang: The Last Airbender", "year": 2026, "type": "movie", "ratingKey": "unreleased"}},
                        {"Metadata": {"title": "Avatar: The Last Airbender", "year": 2005, "type": "show", "ratingKey": "on-netflix"}},
                    ]
                }
            ]
        }
    }
    availabilities = {
        "unreleased": {"MediaContainer": {"size": 0}},
        "on-netflix": {
            "MediaContainer": {
                "Availability": [
                    {"offerType": "subscription", "platform": "netflix", "platformUrl": "https://www.netflix.com/title/70142405"}
                ]
            }
        },
    }

    discover = PlexDiscover(session=None, token="x", region="SE")

    async def fake_get(path, params):
        if path == "/library/search":
            return search
        return availabilities[path.split("/")[3]]

    discover._get = fake_get
    result = asyncio.run(discover.find("avatar aang the last airbender"))
    assert result.rating_key == "on-netflix"
    assert result.availabilities[0].platform == "netflix"


def test_affiliate_redirect_unwrapped():
    response = {
        "MediaContainer": {
            "Availability": [
                {
                    "offerType": "subscription",
                    "platform": "disney-standard",
                    "platformUrl": "https://disneyplus.bn5x.net/c/1/2/3?u=https%3A%2F%2Fwww.disneyplus.com%2Fbrowse%2Fentity-422f",
                }
            ]
        }
    }
    found = _extract_availabilities(response)
    assert found[0].url == "https://www.disneyplus.com/browse/entity-422f"
