"""Assist intent handler.

Loaded automatically by Home Assistant's intent component. Combined with the
custom sentences in custom_sentences/<lang>/plex_assistant.yaml this lets you say
e.g. "spela dune på tv:n" straight to Assist (or via Siri with the HA companion app).
"""

import homeassistant.helpers.config_validation as cv
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from .const import DOMAIN, INTENT_COMMAND
from .handler import async_handle_command


async def async_setup_intents(hass: HomeAssistant) -> None:
    intent.async_register(hass, PlexAssistantCommandIntent())


class PlexAssistantCommandIntent(intent.IntentHandler):
    """Pass the raw spoken command to the Plex Assistant pipeline and speak the result."""

    intent_type = INTENT_COMMAND
    description = "Play movies, shows or music on Plex or an external streaming service"
    slot_schema = {"command": cv.string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        command = slots["command"]["value"]
        response = intent_obj.create_response()

        from homeassistant.config_entries import ConfigEntryState

        entries = [
            e
            for e in intent_obj.hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
        ]
        if not entries:
            response.async_set_speech("Plex Assistant is not configured.")
            return response

        message = await async_handle_command(intent_obj.hass, entries[0], command)
        response.async_set_speech(message)
        return response
