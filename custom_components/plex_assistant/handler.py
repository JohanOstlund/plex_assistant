"""The command pipeline: text in -> speech processing -> device + media resolution -> playback."""

from __future__ import annotations

import asyncio

from homeassistant.core import HomeAssistant

from .const import _LOGGER
from .helpers import (
    filter_media,
    find_media,
    fuzzy,
    get_devices,
    media_error,
    media_service,
    no_device_error,
    play_tts_error,
    remote_control,
    run_start_script,
    seek_to_offset,
)
from .const import APP_CAPABLE, PLEX_CAPABLE
from .models import PlexAssistantConfigEntry
from .players import play_external
from .process_speech import ProcessSpeech
from .router import Route, RouteError, async_route


async def async_handle_command(hass: HomeAssistant, entry: PlexAssistantConfigEntry, text: str) -> str:
    """Handle a spoken/typed command. Returns a message suitable for a voice response."""
    data = entry.runtime_data
    pa = data.pa
    localize = data.localize
    responses = data.responses

    command_text = (text or "").strip().lower()
    if not command_text:
        _LOGGER.warning(localize["no_call"])
        return responses["no_command"]
    _LOGGER.debug("Command: %s", command_text)

    for keyword, replacement in data.keyword_replace.items():
        if keyword.lower() in command_text:
            command_text = command_text.replace(keyword.lower(), replacement.lower())

    get_devices(hass, pa)
    command = await hass.async_add_executor_job(
        lambda: ProcessSpeech(pa, localize, command_text, data.default_device, data.services_config).results
    )
    _LOGGER.debug("Processed command: %s", {i: command[i] for i in command if i != "library" and command[i]})

    if not command["device"] and not data.default_device:
        message = no_device_error(localize)
        _LOGGER.warning(message)
        return message

    def _refresh_library_cache():
        if pa.media["updated"] < pa.library.search(sort="addedAt:desc", limit=1)[0].addedAt:
            type(pa).media.fget.cache_clear()
            _LOGGER.debug("Updated library: %s", pa.media["updated"])

    await hass.async_add_executor_job(_refresh_library_cache)

    device = fuzzy(command["device"] or data.default_device, pa.device_names)
    device = await run_start_script(hass, pa, command, data.start_script, device, data.default_device)

    if device[1] < 60:
        message = no_device_error(localize, command["device"])
        _LOGGER.warning(message)
        return message
    _LOGGER.debug("Device: %s", device[0])

    device_name = device[0]
    device = pa.devices[device_name]

    if command["control"]:
        await remote_control(hass, command["control"], device, data.jump_amount)
        return responses["control_sent"]

    local_result = await hass.async_add_executor_job(find_media, pa, command)

    try:
        route = await async_route(hass, data, command, local_result)
    except RouteError as error:
        message = responses[error.response_key].format(**error.kwargs)
        _LOGGER.warning(message)
        if data.tts_errors and device["device_type"] != "plex":
            await play_tts_error(hass, data.tts_dir, device["entity_id"], message, data.lang)
        return message

    if route.source == "plex":
        if device["device_type"] in PLEX_CAPABLE:
            return await play_on_plex(hass, entry, command, local_result, device, device_name)
        if device["device_type"] in APP_CAPABLE and data.services_config.get("plex", {}).get(device["device_type"]):
            return await play_via_plex_app(hass, entry, command, local_result, device, device_name)
        return responses["no_plex_device"].format(device=device_name)

    return await play_external(hass, data, route, device, device_name)


async def _resolve_media(hass: HomeAssistant, data, command, local_result, device):
    """Turn the local match into a playqueue. Returns (media, offset, error_message)."""
    pa = data.pa

    def _resolve():
        media, library, _score = local_result
        return filter_media(pa, command, media, library)

    try:
        media, offset = await hass.async_add_executor_job(_resolve)
    except Exception as error:  # noqa: BLE001
        _LOGGER.warning("Media lookup failed: %s", error)
        media, offset = None, 0

    if not media:
        error = media_error(command, data.localize)
        _LOGGER.warning(error)
        if data.tts_errors and device["device_type"] != "plex":
            await play_tts_error(hass, data.tts_dir, device["entity_id"], error, data.lang)
        return None, 0, error

    _LOGGER.debug("Media: %s", str(media.items))
    return media, offset, None


def _plex_payload(pa, media, prefixed: bool) -> str:
    # HA's process_plex_payload only reads playqueue_id and plex_server
    return '%s{"playqueue_id": %s, "plex_server": "%s"}' % (
        "plex://" if prefixed else "",
        media.playQueueID,
        pa.server.friendlyName,
    )


def _title_of(media, command) -> str:
    return getattr(media.items[0], "title", command["media"]) if media.items else str(command["media"])


async def play_on_plex(
    hass: HomeAssistant, entry: PlexAssistantConfigEntry, command, local_result, device, device_name
) -> str:
    """Resolve media in the local Plex library and cast it to the target device."""
    data = entry.runtime_data

    media, offset, error = await _resolve_media(hass, data, command, local_result, device)
    if error:
        return error

    payload = _plex_payload(data.pa, media, prefixed=device["device_type"] in ["cast", "sonos"])
    await media_service(hass, device["entity_id"], "play_media", payload)
    entry.async_create_background_task(
        hass, seek_to_offset(hass, offset, device["entity_id"]), "plex_assistant_seek"
    )

    return data.responses["playing"].format(media=_title_of(media, command), device=device_name)


async def play_via_plex_app(
    hass: HomeAssistant, entry: PlexAssistantConfigEntry, command, local_result, device, device_name
) -> str:
    """Launch the Plex app on an app-capable device, then cast once HA sees the Plex client.

    The Plex integration only exposes a client media_player while the app is running,
    so we answer right away and finish the cast in the background.
    """
    data = entry.runtime_data

    media, offset, error = await _resolve_media(hass, data, command, local_result, device)
    if error:
        return error

    title = _title_of(media, command)
    launch = Route(source="plex", title=title, service=data.services_config["plex"], url=None)
    await play_external(hass, data, launch, device, device_name)

    entry.async_create_background_task(
        hass,
        _cast_when_client_appears(hass, data, media, offset, device, device_name),
        "plex_assistant_app_cast",
    )
    return data.responses["opening_plex"].format(media=title, device=device_name)


async def _cast_when_client_appears(hass: HomeAssistant, data, media, offset, device, device_name, timeout=120):
    pa = data.pa
    payload = _plex_payload(pa, media, prefixed=False)
    deadline = hass.loop.time() + timeout

    while hass.loop.time() < deadline:
        get_devices(hass, pa)
        candidates = {}
        for name, info in pa.devices.items():
            if info["device_type"] != "plex":
                continue
            state = hass.states.get(info["entity_id"])
            if state is not None and state.state not in ("unavailable", "unknown"):
                candidates[name] = info

        if candidates:
            match = fuzzy(device_name, list(candidates.keys()))
            if match[1] >= 60:
                entity = candidates[match[0]]["entity_id"]
                _LOGGER.debug("Plex client for %s appeared as %s (%s)", device_name, match[0], entity)
                await media_service(hass, entity, "play_media", payload)
                await seek_to_offset(hass, offset, entity)
                return
        await asyncio.sleep(3)

    message = data.responses["plex_client_timeout"].format(device=device_name)
    _LOGGER.warning(message)
    if data.tts_errors:
        await play_tts_error(hass, data.tts_dir, device["entity_id"], message, data.lang)
