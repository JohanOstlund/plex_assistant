"""The command pipeline: text in -> speech processing -> device + media resolution -> playback."""

from __future__ import annotations

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
from .models import PlexAssistantConfigEntry
from .process_speech import ProcessSpeech


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
        lambda: ProcessSpeech(pa, localize, command_text, data.default_device).results
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

    return await play_on_plex(hass, entry, command, device, device_name)


async def play_on_plex(hass: HomeAssistant, entry: PlexAssistantConfigEntry, command, device, device_name) -> str:
    """Resolve media in the local Plex library and cast it to the target device."""
    data = entry.runtime_data
    pa = data.pa

    def _resolve():
        media, library, _score = find_media(pa, command)
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
        return error

    _LOGGER.debug("Media: %s", str(media.items))

    payload = '%s{"playqueue_id": %s, "type": "%s", "plex_server": "%s"}' % (
        "plex://" if device["device_type"] in ["cast", "sonos"] else "",
        media.playQueueID,
        media.playQueueType,
        pa.server.friendlyName,
    )

    await media_service(hass, device["entity_id"], "play_media", payload)
    entry.async_create_background_task(
        hass, seek_to_offset(hass, offset, device["entity_id"]), "plex_assistant_seek"
    )

    title = getattr(media.items[0], "title", command["media"]) if media.items else str(command["media"])
    return data.responses["playing"].format(media=title, device=device_name)
