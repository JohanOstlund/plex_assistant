# ❱ Plex Assistant v2

Röststyrd uppspelning för Home Assistant: säg vad du vill se, så spelas det från ditt
lokala **Plex**-bibliotek — eller, om titeln (bara) finns på en streamingtjänst, öppnas
**Netflix/Max/Disney+/Viaplay m.fl.** direkt på din TV (Android TV, Apple TV, LG webOS).

Detta är en vidareutveckling av [maykar/plex_assistant](https://github.com/maykar/plex_assistant)
(arkiverat 2021), moderniserad för Home Assistant 2024.10+ / 2026.x. Gamla README för v1
finns i [README_v1.md](README_v1.md).

```
"spela dune på tv:n"                → spelar från Plex (default)
"spela dune på netflix på tv:n"     → tvingar Netflix, även om filmen finns på Plex
"spela dune på plex på tv:n"        → tvingar Plex, även om den finns på Netflix
"spela severance på tv:n"           → finns ej lokalt → hittas på Apple TV+ → appen öppnas
```

## Hur källan väljs

1. **Explicit tjänst i kommandot vinner alltid** ("på netflix", "på plex").
2. Annars gäller **källprioriteten** i integrationens alternativ (kommaseparerad lista,
   default `plex`). Första källan i listan som har titeln används.
3. Finns titeln inte i prioritetslistan: svag lokal träff → Plex; annars valfri
   konfigurerad tjänst som har den (via Plex Discover); annars felmeddelande.

Externa titlar slås upp via Plex Discover (kräver bara att HA:s Plex-integration är
konfigurerad — kontots token återanvänds automatiskt; kan överridas i alternativen).

## Installation

1. Kopiera `custom_components/plex_assistant/` till `/config/custom_components/`
   (eller lägg till detta repo som custom repository i HACS).
2. Starta om HA. Kontrollera att [Plex-integrationen](https://www.home-assistant.io/integrations/plex/) är konfigurerad.
3. *Inställningar → Enheter & tjänster → Lägg till integration → Plex Assistant.*
   Välj språk (`sv`) och standardenhet.
4. För röststyrning: kopiera `custom_sentences/sv/plex_assistant.yaml` till
   `/config/custom_sentences/sv/` och ladda om konversation. Se
   [docs/rost-siri-assist.md](docs/rost-siri-assist.md) för Siri-genvägar och webhook.

### Alternativ (kugghjulet på integrationen)

| Alternativ | Beskrivning |
|---|---|
| Källprioritet | T.ex. `plex, netflix, max` — första som har titeln vinner |
| Region | ISO-landskod för streamingutbud, default `SE` |
| Plex-token | Lämna tomt för att återanvända Plex-integrationens token |
| Start-script / keyword replace / hopplängder | Som i v1, se [README_v1.md](README_v1.md) |

## Enheter

| Uppspelning | Enheter |
|---|---|
| Plex-media | Chromecast/cast-enheter, Sonos, Plex-klienter |
| Streamingappar | Android TV (via `androidtv_remote` eller ADB), Apple TV, LG webOS |

En Chromecast med Google TV kan både casta Plex och öppna appar — integrationsparet
(cast + androidtv_remote) på samma fysiska enhet hittas automatiskt.

**Deep links:** Android TV har bäst stöd (URL öppnar titeln direkt i appen). På LG webOS
deep-linkar Netflix och YouTube; övriga appar startas utan titel. På Apple TV skickas
titelns URL via `launch_app` — hur väl appen tar emot den varierar per app. När deep link
saknas öppnas appen och svaret säger det ("...finns på Disney+. Öppnar appen på TV:n.").

Mappningen tjänst → app-id/deep link ligger i
[`services_config.json`](custom_components/plex_assistant/services_config.json) och kan
överridas utan kodändring via `/config/plex_assistant/services_config.json` (merge:as
över den medföljande). App-id:n för din TV: webOS-appar kan listas med
`webostv.command` → `com.webos.applicationManager/listApps`, Apple TV-appar syns i
media_player-entitetens `source_list`.

## Service och svar

`plex_assistant.command` tar fritext och returnerar svaret (med `return_response`):

```yaml
action: plex_assistant.command
data:
  command: "spela dune på netflix på tv:n"
response_variable: result   # result.response = "Spelar Dune med Netflix på TV:n."
```

Assist-intentet `PlexAssistantCommand` använder samma pipeline och läser upp svaret.

## Kända begränsningar

- Plex Discover-API:t är **odokumenterat** — parsningen är defensiv och loggar rått
  svar på debug-nivå (`logger: custom_components.plex_assistant: debug`) om något ändras.
- App-id:n för webOS/Apple TV i `services_config.json` utgår från kända värden och kan
  behöva justeras för just din TV/region (verifiera med metoderna ovan).
- Google Assistant-stödet från v1 (IFTTT/DialogFlow) är borta — Google lade ner de
  API:erna 2023. Använd Assist/Siri, eller webhook-vägen från Android.

## Utveckling

```bash
python -m venv .venv && .venv/bin/pip install homeassistant plexapi rapidfuzz gTTS pytest
.venv/bin/python -m pytest tests/
```
