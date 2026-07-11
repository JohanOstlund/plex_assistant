import logging

DOMAIN = "plex_assistant"
_LOGGER = logging.getLogger(__package__)

CONF_SERVER_NAME = "server_name"
CONF_DEFAULT_CAST = "default_cast"
CONF_LANGUAGE = "language"
CONF_TTS_ERRORS = "tts_errors"

OPT_SOURCE_PRIORITY = "source_priority"
OPT_REGION = "region"
OPT_PLEX_TOKEN = "plex_token"
OPT_START_SCRIPT = "start_script"
OPT_KEYWORD_REPLACE = "keyword_replace"
OPT_JUMP_FORWARD = "jump_f"
OPT_JUMP_BACK = "jump_b"

DEFAULT_SOURCE_PRIORITY = "plex"
DEFAULT_REGION = "SE"

SERVICE_COMMAND = "command"
INTENT_COMMAND = "PlexAssistantCommand"

# Fuzzy score (0-100) required to consider a title a local Plex match
LOCAL_MATCH_THRESHOLD = 75

# media_player platforms we can target, mapped to internal device types
PLATFORM_MAP = {
    "cast": "cast",
    "sonos": "sonos",
    "plex": "plex",
    "webostv": "webos",
    "apple_tv": "apple_tv",
    "androidtv": "android_tv_adb",
    "androidtv_remote": "android_tv",
}

# Device types that can play local Plex media via media_player.play_media
PLEX_CAPABLE = {"cast", "sonos", "plex"}
# Device types that can launch external streaming apps
APP_CAPABLE = {"android_tv", "android_tv_adb", "apple_tv", "webos"}
