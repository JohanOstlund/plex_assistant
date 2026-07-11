import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er

from .const import (
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
    OPT_PLEX_TOKEN,
    OPT_REGION,
    OPT_SOURCE_PRIORITY,
    OPT_START_SCRIPT,
    PLATFORM_MAP,
)
from .localize import translations


def get_device_names(hass):
    registry = er.async_get(hass)
    names = []
    for entry in registry.entities.values():
        if entry.domain != "media_player" or entry.platform not in PLATFORM_MAP:
            continue
        if entry.disabled_by or entry.hidden_by:
            continue
        state = hass.states.get(entry.entity_id)
        name = (state and state.attributes.get("friendly_name")) or entry.name or entry.original_name
        if name:
            names.append(name)
    return sorted(set(names))


class PlexAssistantFlowHandler(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PlexAssistantOptionsFlowHandler()

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        servers = [x.title for x in self.hass.config_entries.async_entries("plex")]
        if len(servers) < 1:
            return self.async_abort(reason="no_plex_server")

        if user_input is not None:
            server = user_input.get(CONF_SERVER_NAME, servers[0])
            return self.async_create_entry(title=server, data=user_input)

        multi_server_schema = {vol.Optional(CONF_SERVER_NAME): vol.In(servers)} if len(servers) > 1 else {}
        devices = get_device_names(self.hass)
        default_cast_schema = {vol.Optional(CONF_DEFAULT_CAST): vol.In(devices)} if devices else {}
        schema = {
            **multi_server_schema,
            vol.Optional(CONF_LANGUAGE, default="en"): vol.In(sorted(translations.keys())),
            **default_cast_schema,
            vol.Optional(CONF_TTS_ERRORS, default=True): bool,
        }
        return self.async_show_form(step_id="user", data_schema=vol.Schema(schema))


class PlexAssistantOptionsFlowHandler(OptionsFlow):
    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.config_entry.options, **user_input})

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        OPT_SOURCE_PRIORITY,
                        description={
                            "suggested_value": options.get(OPT_SOURCE_PRIORITY, DEFAULT_SOURCE_PRIORITY)
                        },
                        default=DEFAULT_SOURCE_PRIORITY,
                    ): str,
                    vol.Optional(
                        OPT_REGION,
                        description={"suggested_value": options.get(OPT_REGION, DEFAULT_REGION)},
                        default=DEFAULT_REGION,
                    ): str,
                    vol.Optional(
                        OPT_PLEX_TOKEN,
                        description={"suggested_value": options.get(OPT_PLEX_TOKEN, "")},
                        default="",
                    ): str,
                    vol.Optional(
                        OPT_START_SCRIPT,
                        description={"suggested_value": options.get(OPT_START_SCRIPT, "")},
                        default="",
                    ): str,
                    vol.Optional(
                        OPT_KEYWORD_REPLACE,
                        description={"suggested_value": options.get(OPT_KEYWORD_REPLACE, "")},
                        default="",
                    ): str,
                    vol.Required(OPT_JUMP_FORWARD, default=options.get(OPT_JUMP_FORWARD, 30)): int,
                    vol.Required(OPT_JUMP_BACK, default=options.get(OPT_JUMP_BACK, 15)): int,
                }
            ),
        )
