# Health Assistant — Telegram Bot

Persönlicher Fitness-Assistent für Garmin, Renpho & Google Fit.
Läuft als Docker-Container auf dem Intel NUC neben Home Assistant.

## Setup

### 1. Telegram Bot erstellen
1. @BotFather in Telegram öffnen → `/newbot`
2. Token kopieren → `TELEGRAM_BOT_TOKEN`
3. Eigene Chat-ID herausfinden: @userinfobot schreiben → `TELEGRAM_CHAT_ID`

### 2. OpenAI API Key
- platform.openai.com → API Keys → neuen Key erstellen

### 3. Google Fit OAuth2 (optional, für Schritte ohne Uhr)
1. Google Cloud Console → Neues Projekt
2. "Google Fitness API" aktivieren
3. OAuth2 Credentials (Desktop App) erstellen
4. `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` kopieren
5. Beim ersten Start läuft ein Browser-OAuth-Flow

### 4. Konfiguration
```bash
cp .env.example .env
# .env mit deinen Daten befüllen
```

### 5. Starten
```bash
# Auf dem NUC:
docker-compose up -d

# Logs verfolgen:
docker-compose logs -f
```

### 6. Erster Start — Garmin Auth
Beim ersten Start wird Garmin via Session-Login authentifiziert.
Der Token wird in `./data/.garminconnect` gespeichert und automatisch erneuert.

Falls MFA aktiv ist, muss `prompt_mfa` in `connectors/garmin.py` angepasst werden
(einmaliger interaktiver Login, danach Token-basiert).

## Befehle

| Befehl | Funktion |
|--------|----------|
| `/hilfe` | Alle Befehle |
| `/heute` | Tages-Snapshot (Schlaf, Steps, Body Battery) |
| `/erholung` | HRV, Body Battery, Training Readiness |
| `/training` | Letzte 5 Aktivitäten |
| `/woche` | Wöchentliche Zusammenfassung |
| `/gewicht` | Renpho Körperkomposition & 30-Tage-Trend |
| `/tipps` | GPT-4o Trainingstipp |
| `/status` | Schnellübersicht |

## Automatische Nachrichten

| Zeit | Inhalt |
|------|--------|
| 07:30 täglich | Morgen-Briefing (Schlaf, HRV, Empfehlung) |
| 20:00 täglich | Abend-Zusammenfassung (Schritte, Workouts) |
| Sonntag 18:00 | Wochen-Review mit GPT-4o |
| 07:30 (konditional) | Renpho-Erinnerung wenn >5 Tage keine Messung |

## Datenquellen & Deduplication

- **Garmin** (primär): Alle Aktivitäten, Schlaf, HRV, Body Battery, Schritte
- **Renpho** (Körperdaten): Gewicht, Körperfett, Muskelmasse — gecacht in SQLite
- **Google Fit** (Fallback): Nur Schritte wenn Garmin nicht getragen wurde

Garmin-Schritte haben immer Priorität. Google Fit wird nur genutzt wenn
Garmin < 500 Schritte für den Tag meldet (= Uhr nicht getragen).

## Projektstruktur

```
health-assistant/
├── connectors/      # Garmin, Renpho, Google Fit API-Wrapper
├── analytics/       # Insights, Deduplication, Text-Formatter
├── ai/              # OpenAI GPT-4o Client
├── bot/             # aiogram Handlers + APScheduler
├── storage/         # SQLite Datenbank
└── data/            # Persistente Daten (gitignored)
```
