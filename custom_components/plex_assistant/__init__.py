"""
Plex Assistant is a Home Assistant integration for casting Plex media (and, when a
title is only available on an external streaming service, launching that service's
app on your TV) using voice commands from Assist, Siri Shortcuts, or any automation
that can call a service.

https://github.com/JohanOstlund/plex_assistant
"""

from __future__ import annotations

import os

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv

from .const import (
    _LOGGER,
    CONF_DEFAULT_CAST,
    CONF_LANGUAGE,
    CONF_SERVER_NAME,
    CONF_TTS_ERRORS,
    DEFAULT_REGION,
    DEFAULT_SOURCE_PRIORITY,
    DOMAIN,
    OPT_JUMP_BACK,
    OPT_JUMP_FORWARD,
    OPT_KEYWORD_REPLACE,
    OPT_REGION,
    OPT_SOURCE_PRIORITY,
    OPT_START_SCRIPT,
    SERVICE_COMMAND,
)
from .handler import async_handle_command
from .helpers import get_devices, get_server, process_config_item
from .localize import translations
from .models import PlexAssistantConfigEntry, PlexAssistantData
from .plex_assistant import PlexAssistant
from .responses import get_responses

SERVICE_SCHEMA = vol.Schema({vol.Required("command"): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: PlexAssistantConfigEntry) -> bool:
    lang = entry.data.get(CONF_LANGUAGE, "en")
    start_script = process_config_item(entry.options, OPT_START_SCRIPT)

    server = await get_server(hass, entry.data.get(CONF_SERVER_NAME))
    if not server:
        raise ConfigEntryNotReady("Plex server not available")

    pa = await hass.async_add_executor_job(PlexAssistant, server, list(start_script.keys()))
    get_devices(hass, pa)
    _LOGGER.debug("Media titles: %s", len(pa.media["all_titles"]))

    tts_errors = entry.data.get(CONF_TTS_ERRORS, True)
    tts_dir = hass.config.path("www/plex_assist_tts/")
    if tts_errors and not os.path.exists(tts_dir):
        await hass.async_add_executor_job(lambda: os.makedirs(tts_dir, mode=0o777, exist_ok=True))

    priority = entry.options.get(OPT_SOURCE_PRIORITY, DEFAULT_SOURCE_PRIORITY)
    entry.runtime_data = PlexAssistantData(
        pa=pa,
        lang=lang,
        localize=translations[lang],
        responses=get_responses(lang),
        default_device=entry.data.get(CONF_DEFAULT_CAST),
        tts_errors=tts_errors,
        tts_dir=tts_dir,
        start_script=start_script,
        keyword_replace=process_config_item(entry.options, OPT_KEYWORD_REPLACE),
        jump_amount=[entry.options.get(OPT_JUMP_FORWARD) or 30, entry.options.get(OPT_JUMP_BACK) or 15],
        source_priority=[s.strip().lower() for s in priority.split(",") if s.strip()],
        region=entry.options.get(OPT_REGION, DEFAULT_REGION),
    )

    async def handle_command_service(call: ServiceCall):
        message = await async_handle_command(hass, entry, call.data["command"])
        if call.return_response:
            return {"response": message}
        return None

    hass.services.async_register(
        DOMAIN,
        SERVICE_COMMAND,
        handle_command_service,
        schema=SERVICE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PlexAssistantConfigEntry) -> bool:
    hass.services.async_remove(DOMAIN, SERVICE_COMMAND)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: PlexAssistantConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
