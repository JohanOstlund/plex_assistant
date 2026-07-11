# Plex Assistant v2 — projektkontext

Johans fork av [maykar/plex_assistant](https://github.com/maykar/plex_assistant) (arkiverat 2021),
omskriven som v2 i juli 2026 på branchen `v2`: moderniserad för HA 2026.x, röst via Assist
custom sentences + Siri Shortcuts (Google-vägen är död sedan DialogFlow lades ner 2023), och
routing mellan lokalt Plex och externa streamingtjänster via Plex Discover.

## Kärnkrav (får inte brytas)

Johan ska kunna **välja** källa: "på plex"/"på netflix" i kommandot tvingar den källan även
när titeln finns på båda. Utan explicit tjänst gäller konfigurerbar källprioritet
(option `source_priority`, default `plex`). Fallback-only-routing är alltså fel design här.

Routingpolicyn ligger i `custom_components/plex_assistant/router.py`:
1. Explicit tjänst i kommandot vinner alltid.
2. Annars första källan i prioritetslistan som har titeln.
3. Sist: svag lokal träff (score ≥ 60) → Plex; annars valfri konfigurerad tjänst med
   titeln via Discover; annars fel.

## Arkitektur

- `handler.py` — kommandopipeline: keyword replace → ProcessSpeech → lokal fuzzy-match →
  `async_route` → `play_on_plex` (v1-kompatibel `plex://{json}`-payload) eller `play_external`.
- `sources/plex_discover.py` — **odokumenterat** Plex Discover-API
  (`metadata.provider.plex.tv`); parsning är defensiv (JSON-vandring) och loggar rått svar
  på debug-nivå. Token återanvänds från HA:s Plex-integration om inget anges i options.
- `players.py` — externa appar: Android TV (`remote.turn_on` med deep link, alt. ADB),
  Apple TV (`play_media` typ `app`), LG webOS (`webostv.command system.launcher/launch`).
  Mappning tjänst → app-id/deep link i `services_config.json`, överridbar via
  `/config/plex_assistant/services_config.json`.
- `process_speech.py` + `localize.py` — behållna från v1 (svenska komplett), utökade med
  tjänst-extrahering ("på netflix").
- `intent.py` + `custom_sentences/{sv,en}/` — Assist-intentet `PlexAssistantCommand`.
- `models.py` — `entry.runtime_data` (`PlexAssistantConfigEntry`).

## Johans miljö

- Senaste HA (verifierat mot HA 2026.2.3 i `.venv`).
- Enheter: Android TV, Apple TV, LG OLED C9 (webOS 4.5 — gammal, kan ha egenheter).
- Språk: svenska (`sv`), region `SE`.

## Utveckling & test

```bash
python -m venv .venv && .venv/bin/pip install homeassistant plexapi rapidfuzz gTTS pytest
.venv/bin/python -m pytest tests/
```

25 enhetstester i `tests/` (router-policy, speech-extrahering, players, Discover-parsning).
Verifiera nya HA-API-anrop mot källan i `.venv/lib/.../homeassistant/` innan de används —
så gjordes alla service-anrop i `players.py`.

## Johans enhetstopologi (verifierad 2026-07-11 mot HA:s register)

Vardagsrummet (area `allrum`) har BÅDE en Apple TV 4K och en NVIDIA Shield på TV:n:
- Shield exponeras som `media_player.shield` (cast, Chromecast inbyggt), `plex_shield`
  (plex-klient), `nvidia_shield` (androidtv/ADB) och `shield_2`+`remote.shield`
  (androidtv_remote) — alla med olika `device_id`, så syskon-länkning via device_id funkar
  inte för Shield.
- Apple TV = `media_player.allrum_2` (apple_tv). Rummets enda cast-enhet är en Nest Mini
  (endast ljud). **Apple TV kan inte fjärrstyras tillförlitligt för Plex** (Plex Companion
  ger `/clients`=0, klienten blir aldrig kontrollerbar). tvOS Companion "Open URL" vägrar
  godtyckliga https-länkar → starta appar via bundle-id, inte deep-link-URL.

Därför: Plex-routing väljer en castbar enhet i **samma HA-area** (cast > plex-klient) i
stället för app-start-och-vänta. Kräver att enheterna har en area i HA.

## Ej verifierat mot riktig hårdvara än

- webOS/Apple TV app-id:n i `services_config.json` för Johans TV/region
  (inkl. Plex-appens webOS-id `cdp-30`).
- Cast av `plex://{json}` till Shield (cast) resp. Plex-klient i live-uppspelning.
- Deep-link-träff i streamingapparna (att rätt titel öppnas, inte bara appen).

Discover-API:t är **verifierat mot live-API:t 2026-07-11** (token från HA:s Plex-integration,
region SE): sök på `discover.provider.plex.tv/library/search`, availabilities på
`/library/metadata/{rk}/availabilities?country=SE` → `MediaContainer.Availability[]` med
`platform`/`platformUrl`/`offerType`. Verkliga plattformsnamn: `disney-standard`,
`appletv`, `netflix`, `max`, `hbo-max-amazon-channel`. Affiliate-wrappers (`?u=`) packas
upp, rent/buy-erbjudanden filtreras bort.

## Historik

v2 byggdes i fem commits: Fas 0 (HA 2026-modernisering), Fas 1 (Assist/Siri), Fas 2
(router + Discover), Fas 3 (externa spelare), Fas 4 (tester/README). Gamla README:
`README_v1.md`.
