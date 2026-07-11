from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .plex_assistant import PlexAssistant


@dataclass
class PlexAssistantData:
    pa: PlexAssistant
    lang: str
    localize: dict[str, Any]
    responses: dict[str, str]
    default_device: str | None
    tts_errors: bool
    tts_dir: str
    start_script: dict[str, str]
    keyword_replace: dict[str, str]
    jump_amount: list[int]
    source_priority: list[str] = field(default_factory=lambda: ["plex"])
    region: str = "SE"
    discover: Any = None
    services_config: dict[str, Any] = field(default_factory=dict)


type PlexAssistantConfigEntry = ConfigEntry[PlexAssistantData]
