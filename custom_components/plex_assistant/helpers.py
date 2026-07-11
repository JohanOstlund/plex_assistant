import asyncio
import re

from rapidfuzz import fuzz, process
from json import JSONDecodeError, loads

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import _LOGGER, PLATFORM_MAP


def fuzzy(media, lib, scorer=fuzz.QRatio):
    if isinstance(lib, list) and len(lib) > 0:
        return process.extractOne(media, lib, scorer=scorer) or ["", 0]
    return ["", 0]


def process_config_item(options, option_type):
    option = options.get(option_type)
    if not option:
        return {}
    try:
        option = loads("{" + option + "}")
        for i in option.keys():
            _LOGGER.debug(f"{option_type} {i}: {option[i]}")
    except (TypeError, AttributeError, KeyError, JSONDecodeError):
        _LOGGER.warning(f"There is a formatting error in the {option_type.replace('_', ' ')} config.")
        option = {}
    return option


async def get_server(hass: HomeAssistant, server_name):
    """Get a plexapi server instance, preferring the HA Plex integration's connection."""
    try:
        from homeassistant.components.plex.services import get_plex_server

        return get_plex_server(hass, plex_server_name=server_name or None)._plex_server
    except (HomeAssistantError, ImportError, AttributeError, KeyError) as error:
        _LOGGER.debug("Falling back to direct Plex connection: %s", error)

    entries = hass.config_entries.async_entries("plex")
    if not entries:
        _LOGGER.warning(
            "Plex Assistant: No Plex server found. Ensure that you've setup the HA "
            "Plex integration and the server is reachable."
        )
        return None

    server_config = entries[0].data.get("server_config", {})
    url = server_config.get("url")
    token = server_config.get("token")
    verify_ssl = server_config.get("verify_ssl", True)
    if not url or not token:
        _LOGGER.warning("Plex Assistant: Could not read connection details from the Plex integration.")
        return None

    def _connect():
        import requests
        from plexapi.server import PlexServer

        session = None
        if not verify_ssl:
            session = requests.Session()
            session.verify = False
        return PlexServer(url, token, session=session)

    try:
        return await hass.async_add_executor_job(_connect)
    except Exception as error:  # noqa: BLE001
        _LOGGER.warning("Plex Assistant: Could not connect to Plex server: %s", error)
        return None


def get_plex_account_token(hass: HomeAssistant):
    """Reuse the plex.tv account token stored by the HA Plex integration (for Discover)."""
    for entry in hass.config_entries.async_entries("plex"):
        token = entry.data.get("server_config", {}).get("token")
        if token:
            return token
    return None


def get_devices(hass: HomeAssistant, pa):
    """Collect targetable media players from the entity registry. Must run on the event loop."""
    registry = er.async_get(hass)
    for entry in registry.entities.values():
        if entry.domain != "media_player" or entry.platform not in PLATFORM_MAP:
            continue
        if entry.disabled_by or entry.hidden_by:
            continue
        state = hass.states.get(entry.entity_id)
        if state is None:
            continue
        name = state.attributes.get("friendly_name") or entry.name or entry.original_name
        if not name:
            continue
        pa.devices[name] = {
            "entity_id": entry.entity_id,
            "device_type": PLATFORM_MAP[entry.platform],
            "device_id": entry.device_id,
        }


def find_entity_for_device(hass: HomeAssistant, device_id, domain, platforms):
    """Find a sibling entity (e.g. the remote.* of an Android TV) on the same physical device."""
    if not device_id:
        return None
    registry = er.async_get(hass)
    for entry in registry.entities.values():
        if entry.device_id == device_id and entry.domain == domain and entry.platform in platforms:
            if not entry.disabled_by:
                return entry.entity_id
    return None


async def run_start_script(hass: HomeAssistant, pa, command, start_script, device, default_device):
    if device[0] in start_script.keys():
        await hass.services.async_call(
            "script", "turn_on", {"entity_id": f"script.{start_script[device[0]]}"}, blocking=True
        )
        get_devices(hass, pa)
        return fuzzy(command["device"] or default_device, pa.device_names)
    return device


async def media_service(hass: HomeAssistant, entity_id, call, payload=None):
    args = {"entity_id": entity_id}
    if call == "play_media":
        args = {**args, **{"media_content_type": "video", "media_content_id": payload}}
    elif call == "media_seek":
        args = {**args, **{"seek_position": payload}}
    await hass.services.async_call("media_player", call, args)


async def jump(hass: HomeAssistant, device, amount):
    if device["device_type"] == "plex":
        await media_service(hass, device["entity_id"], "media_pause")
        await asyncio.sleep(0.5)

    offset = hass.states.get(device["entity_id"]).attributes.get("media_position", 0) + amount
    await media_service(hass, device["entity_id"], "media_seek", offset)

    if device["device_type"] == "plex":
        await media_service(hass, device["entity_id"], "media_play")


async def remote_control(hass: HomeAssistant, control, device, jump_amount):
    if control == "jump_forward":
        await jump(hass, device, jump_amount[0])
    elif control == "jump_back":
        await jump(hass, device, -jump_amount[1])
    else:
        await media_service(hass, device["entity_id"], f"media_{control}")


async def seek_to_offset(hass: HomeAssistant, offset, entity):
    if offset < 1:
        return
    timeout = 0
    while not hass.states.is_state(entity, "playing") and timeout < 100:
        await asyncio.sleep(0.10)
        timeout += 1

    timeout = 0
    if hass.states.is_state(entity, "playing"):
        await media_service(hass, entity, "media_pause")
        while not hass.states.is_state(entity, "paused") and timeout < 100:
            await asyncio.sleep(0.10)
            timeout += 1

    if hass.states.is_state(entity, "paused"):
        if hass.states.get(entity).attributes.get("media_position", 0) < 9:
            await media_service(hass, entity, "media_seek", offset)
        await media_service(hass, entity, "media_play")


def no_device_error(localize, device=None):
    device = f': "{device.title()}".' if device else "."
    return f"{localize['cast_device'].capitalize()} {localize['not_found']}{device}"


def media_error(command, localize):
    error = "".join(
        f"{localize[keyword]['keywords'][0]} " for keyword in ["latest", "unwatched", "ondeck"] if command[keyword]
    )
    if command["media"]:
        media = command["media"]
        media = media if isinstance(media, str) else getattr(media, "title", str(media))
        error += f"{media.capitalize()} "
    elif command["library"]:
        error += f"{localize[command['library']+'s'][0]} "
    for keyword in ["season", "episode"]:
        if command[keyword]:
            error += f"{localize[keyword]['keywords'][0]} {command[keyword]} "
    error += f"{localize['not_found']}."
    return error.capitalize()


async def play_tts_error(hass: HomeAssistant, tts_dir, device, error, lang):
    def _save():
        from gtts import gTTS

        tts = gTTS(error, lang=lang)
        tts.save(tts_dir + "error.mp3")

    await hass.async_add_executor_job(_save)
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": device,
            "media_content_type": "audio/mp3",
            "media_content_id": "/local/plex_assist_tts/error.mp3",
        },
    )


def filter_media(pa, command, media, library):
    offset = 0

    if library == "playlist":
        media = pa.server.playlist(media) if media else pa.server.playlists()
    elif media or library:
        media = pa.library.search(title=media or None, libtype=library or None)

    if isinstance(media, list) and len(media) == 1:
        media = media[0]

    if command["episode"]:
        media = media.episode(season=int(command["season"] or 1), episode=int(command["episode"]))
    elif command["season"]:
        media = media.season(season=int(command["season"]))

    if command["ondeck"]:
        title, libtype = [command["media"], command["library"]]
        if getattr(media, "onDeck", None):
            media = media.onDeck()
        elif title or libtype:
            search_result = pa.library.search(title=title or None, libtype=libtype or None, limit=1)[0]
            if getattr(search_result, "onDeck", None):
                media = search_result.onDeck()
            else:
                media = pa.library.sectionByID(search_result.librarySectionID).onDeck()
        else:
            media = pa.library.sectionByID(pa.tv_id).onDeck() + pa.library.sectionByID(pa.movie_id).onDeck()
            media.sort(key=lambda x: getattr(x, "addedAt", None), reverse=False)

    if command["unwatched"]:
        if isinstance(media, list) or (not media and not library):
            media = media[:200] if isinstance(media, list) else pa.library.recentlyAdded()
            media = [x for x in media if getattr(x, "viewCount", 0) == 0]
        elif getattr(media, "unwatched", None):
            media = media.unwatched()[:200]

    if command["latest"] and not command["unwatched"]:
        if library and not media and pa.section_id[library]:
            media = pa.library.sectionByID(pa.section_id[library]).recentlyAdded()[:200]
        elif not media:
            media = pa.library.sectionByID(pa.tv_id).recentlyAdded()
            media += pa.library.sectionByID(pa.movie_id).recentlyAdded()
            media.sort(key=lambda x: getattr(x, "addedAt", None), reverse=True)
            media = media[:200]
    elif command["latest"]:
        if getattr(media, "type", None) in ["show", "season"]:
            media = media.episodes()[-1]
        elif isinstance(media, list):
            media = media[:200]
            media.sort(key=lambda x: getattr(x, "addedAt", None), reverse=True)

    if not command["random"] and media:
        pos = getattr(media[0], "viewOffset", 0) if isinstance(media, list) else getattr(media, "viewOffset", 0)
        offset = (pos / 1000) - 5 if pos > 15 else 0

    if getattr(media, "TYPE", None) == "show":
        unwatched = media.unwatched()[:30]
        media = unwatched if unwatched and not command["random"] else media.episodes()[:30]
    elif getattr(media, "TYPE", None) == "episode":
        episodes = media.show().episodes()
        episodes = episodes[episodes.index(media) : episodes.index(media) + 30]
        media = pa.server.createPlayQueue(episodes, shuffle=int(command["random"]))
    elif getattr(media, "TYPE", None) in ["artist", "album"]:
        tracks = media.tracks()
        media = pa.server.createPlayQueue(tracks, shuffle=int(command["random"]))
    elif getattr(media, "TYPE", None) == "track":
        tracks = media.album().tracks()
        tracks = tracks[tracks.index(media) :]
        media = pa.server.createPlayQueue(tracks, shuffle=int(command["random"]))

    if getattr(media, "TYPE", None) != "playqueue" and media:
        media = pa.server.createPlayQueue(media, shuffle=int(command["random"]))

    return [media, 0 if media and media.items[0].listType == "audio" else offset]


def roman_numeral_test(media, lib):
    regex = re.compile(r"\b(\d|(10))\b")
    replacements = {
        "1": "I",
        "2": "II",
        "3": "III",
        "4": "IV",
        "5": "V",
        "6": "VI",
        "7": "VII",
        "8": "VIII",
        "9": "IX",
        "10": "X",
    }

    if len(re.findall(regex, media)) > 0:
        replaced = re.sub(regex, lambda m: replacements[m.group(1)], media)
        return fuzzy(replaced, lib, fuzz.WRatio)
    return ["", 0]


def find_media(pa, command):
    """Search the local Plex library. Returns [result, library, score]."""
    result = ""
    lib = ""
    score = 0
    if getattr(command["media"], "type", None) in ["artist", "album", "track"]:
        return [command["media"], command["media"].type, 100]
    if command["library"]:
        lib_titles = pa.media[f"{command['library']}_titles"]
        if command["media"]:
            standard = fuzzy(command["media"], lib_titles, fuzz.WRatio)
            roman_test = roman_numeral_test(command["media"], lib_titles)
            winner = standard if standard[1] > roman_test[1] else roman_test
            result, score = winner[0], winner[1]
    elif command["media"]:
        item = {}
        scores = {}
        for category in ["show", "movie", "artist", "album", "track", "playlist"]:
            lib_titles = pa.media[f"{category}_titles"]
            standard = fuzzy(command["media"], lib_titles, fuzz.WRatio) if lib_titles else ["", 0]
            roman = roman_numeral_test(command["media"], lib_titles) if lib_titles else ["", 0]

            winner = standard if standard[1] > roman[1] else roman
            item[category] = winner[0]
            scores[category] = winner[1]

        winning_category = max(scores, key=scores.get)
        result = item[winning_category]
        score = scores[winning_category]
        lib = winning_category

    return [result, lib or command["library"], score]
