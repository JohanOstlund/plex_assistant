"""Localized response messages spoken/returned by Assist, Siri and the service call.

Only languages listed here get localized responses; anything else falls back to English.
"""

RESPONSES = {
    "en": {
        "playing": "Playing {media} on {device}.",
        "playing_external": "Playing {media} with {service} on {device}.",
        "opening_app": "{media} is available on {service}. Opening the app on {device}.",
        "not_found": "{media} was not found.",
        "not_on_service": "{media} was not found on {service}.",
        "no_app_device": "{device} can not open streaming apps.",
        "no_plex_device": "{device} can not play Plex media.",
        "control_sent": "OK.",
        "no_command": "No command was received.",
    },
    "sv": {
        "playing": "Spelar {media} på {device}.",
        "playing_external": "Spelar {media} med {service} på {device}.",
        "opening_app": "{media} finns på {service}. Öppnar appen på {device}.",
        "not_found": "{media} hittades inte.",
        "not_on_service": "{media} hittades inte på {service}.",
        "no_app_device": "{device} kan inte öppna streamingappar.",
        "no_plex_device": "{device} kan inte spela Plex-media.",
        "control_sent": "Okej.",
        "no_command": "Inget kommando mottogs.",
    },
}


def get_responses(lang):
    return {**RESPONSES["en"], **RESPONSES.get(lang, {})}
