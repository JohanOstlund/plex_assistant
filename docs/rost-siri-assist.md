# Röststyrning: Assist och Siri

Plex Assistant tar emot fritext via servicen `plex_assistant.command`. Alla vägar nedan
landar där — välj den som passar.

## 1. Home Assistant Assist (grunden)

1. Kopiera `custom_sentences/sv/plex_assistant.yaml` från det här repot till
   `/config/custom_sentences/sv/plex_assistant.yaml` (skapa mappen om den saknas).
2. Starta om Home Assistant (eller kör *Utvecklarverktyg → YAML → Ladda om konversation*).
3. Testa i Assist-dialogen: `spela dune på tv:n`.

Exempel på kommandon:

| Kommando | Vad som händer |
|---|---|
| `spela dune på tv:n` | Spelar från källan med högst prioritet (default Plex) |
| `spela dune på netflix på tv:n` | Tvingar Netflix även om filmen finns på Plex |
| `spela dune på plex på tv:n` | Tvingar Plex även om den finns externt |
| `spela senaste avsnittet av severance på tv:n` | Plex-bibliotekslogik som vanligt |

## 2. Siri (via HA companion-appen)

Enklaste vägen — Assist direkt:

1. Installera HA-appen på iPhone och logga in.
2. Öppna Genvägar (Shortcuts) → ny genväg → lägg till appen Home Assistants
   **Assist**-åtgärd (välj din HA-server och Assist-pipeline).
3. Döp genvägen till t.ex. **Spela film** — namnet blir Siri-frasen.
4. Säg: *"Hey Siri, spela film"* → Siri öppnar Assist → säg *"spela dune på tv:n"*.

Alternativ med dikterad fritext i ett steg:

1. Ny genväg → åtgärden **Fråga efter inmatning** (prompt: *"Vad vill du spela?"*).
   När genvägen körs via Siri ställs frågan med rösten och svaret dikteras.
2. Lägg till Home Assistant-appens åtgärd för att anropa en tjänst/utföra åtgärd
   (heter **Call Service** eller **Perform Action** beroende på appversion) med:
   - Tjänst: `plex_assistant.command`
   - Data: `{"command": "<Angiven inmatning>"}` (välj variabeln från steg 1)
3. Döp genvägen, klart.

## 3. Webhook (fallback, funkar från vad som helst)

Skapa en automation i HA:

```yaml
alias: Plex Assistant webhook
triggers:
  - trigger: webhook
    webhook_id: plex-assistant-kommandon   # byt till något eget/hemligt
    allowed_methods: [POST]
    local_only: true                        # sätt false om du anropar via Nabu Casa
actions:
  - action: plex_assistant.command
    data:
      command: "{{ trigger.json.command }}"
```

Anropa sedan från valfri klient (t.ex. en genväg med *Hämta innehåll från URL*):

```
POST https://<din-ha>/api/webhook/plex-assistant-kommandon
Content-Type: application/json

{"command": "spela dune på tv:n"}
```

## 4. Google

Google Assistant/Gemini har idag ingen bra väg för fritext-vidarebefordran till HA
(DialogFlow/Conversational Actions lades ner 2023). Om du exponerar HA via Google Home
kan du styra mediaspelare, men fritext-kommandon till Plex Assistant får vänta tills
Googles Gemini-integrationer mognar. Webhook-vägen ovan fungerar dock från en
Android-telefon via t.ex. HA-appens widgets eller Tasker.
