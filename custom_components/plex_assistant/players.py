"""Launch external streaming apps on TVs via Home Assistant integrations.

Graceful degradation: deep link straight into the title when a template exists for
the service+platform, otherwise just launch the app so the user can pick the title.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import _LOGGER
from .helpers import find_entity_for_device
from .router import Route


def _extract_id(url: str) -> str:
    return url.rstrip("/").split("/")[-1].split("?")[0]


def _build(template: str | None, url: str | None) -> str | None:
    if not template or not url:
        return None
    return template.format(url=url, id=_extract_id(url))


async def play_external(hass: HomeAssistant, data, route: Route, device, device_name: str) -> str:
    """Open route.service on the target device, deep-linked to route.url when possible."""
    service_name = route.service.get("name", route.source)
    device_type = device["device_type"]

    try:
        # A Chromecast entity may be the cast side of an Android/Google TV; apps are
        # launched through the sibling remote entity on the same physical device.
        if device_type in ("cast", "android_tv"):
            remote_entity = find_entity_for_device(hass, device.get("device_id"), "remote", {"androidtv_remote"})
            if remote_entity:
                return await _play_android_tv(hass, data, route, remote_entity, service_name, device_name)
            if device_type == "cast":
                return data.responses["no_app_device"].format(device=device_name)

        if device_type == "android_tv_adb":
            return await _play_android_tv_adb(hass, data, route, device, service_name, device_name)
        if device_type == "apple_tv":
            return await _play_apple_tv(hass, data, route, device, service_name, device_name)
        if device_type == "webos":
            return await _play_webos(hass, data, route, device, service_name, device_name)
    except Exception as error:  # noqa: BLE001
        _LOGGER.warning("Launching %s on %s failed: %s", service_name, device_name, error)
        return data.responses["launch_failed"].format(service=service_name, device=device_name)

    return data.responses["no_app_device"].format(device=device_name)


def _respond(data, route, service_name, device_name, deep_linked: bool) -> str:
    if deep_linked:
        return data.responses["playing_external"].format(
            media=route.title, service=service_name, device=device_name
        )
    return data.responses["opening_app"].format(media=route.title, service=service_name, device=device_name)


async def _play_android_tv(hass, data, route, remote_entity, service_name, device_name) -> str:
    cfg = route.service.get("android_tv", {})
    link = _build(cfg.get("deep_link"), route.url) or cfg.get("package")
    if not link:
        return data.responses["no_service_mapping"].format(service=service_name, device=device_name)
    _LOGGER.debug("Android TV launch via %s: %s", remote_entity, link)
    await hass.services.async_call(
        "remote", "turn_on", {"entity_id": remote_entity, "activity": link}, blocking=True
    )
    return _respond(data, route, service_name, device_name, deep_linked=bool(cfg.get("deep_link") and route.url))


async def _play_android_tv_adb(hass, data, route, device, service_name, device_name) -> str:
    cfg = route.service.get("android_tv_adb", {})
    link = _build(cfg.get("deep_link"), route.url)
    package = cfg.get("package")
    if link:
        command = f'am start -a android.intent.action.VIEW -d "{link}"'
        if package:
            command += f" {package}"
    elif package:
        command = f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
    else:
        return data.responses["no_service_mapping"].format(service=service_name, device=device_name)
    _LOGGER.debug("Android TV ADB launch on %s: %s", device["entity_id"], command)
    await hass.services.async_call(
        "androidtv", "adb_command", {"entity_id": device["entity_id"], "command": command}, blocking=True
    )
    return _respond(data, route, service_name, device_name, deep_linked=bool(link))


async def _play_apple_tv(hass, data, route, device, service_name, device_name) -> str:
    # tvOS Companion "Open URL" only accepts app bundle ids / registered schemes; arbitrary
    # https deep links raise "Open URL failed", so launch by bundle id and let the app resume.
    cfg = route.service.get("apple_tv", {})
    link = cfg.get("app_id") or _build(cfg.get("deep_link"), route.url)
    if not link:
        return data.responses["no_service_mapping"].format(service=service_name, device=device_name)
    _LOGGER.debug("Apple TV launch on %s: %s", device["entity_id"], link)
    await hass.services.async_call(
        "media_player",
        "play_media",
        {"entity_id": device["entity_id"], "media_content_type": "app", "media_content_id": link},
        blocking=True,
    )
    return _respond(data, route, service_name, device_name, deep_linked=False)


async def _play_webos(hass, data, route, device, service_name, device_name) -> str:
    cfg = route.service.get("webos", {})
    app_id = cfg.get("app_id")
    if not app_id:
        return data.responses["no_service_mapping"].format(service=service_name, device=device_name)
    payload = {"id": app_id}
    content_id = _build(cfg.get("content_id"), route.url)
    if content_id:
        payload["contentId"] = content_id
    _LOGGER.debug("webOS launch on %s: %s", device["entity_id"], payload)
    await hass.services.async_call(
        "webostv",
        "command",
        {"entity_id": device["entity_id"], "command": "system.launcher/launch", "payload": payload},
        blocking=True,
    )
    return _respond(data, route, service_name, device_name, deep_linked=bool(content_id))
