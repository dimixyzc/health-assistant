# Health Assistant — Garmin, Renpho & ChatGPT Coach

Persönlicher Gesundheitsassistent für Garmin, Renpho & Google Fit.

## Knie-Reha-Modus

Der Assistent ist standardmäßig auf die Zeit nach einer Knie-Operation eingestellt.
Er priorisiert Schlaf, Erholung, Stress, HRV, Ruhepuls, Body Battery und
Körperdaten. Schritte, Gym und Cardio werden nur als Kontext gezeigt — es gibt
keine Schritt- oder Trainingsziele und keine Belastungsempfehlungen. Der Reha-
Plan des Behandlungsteams hat immer Vorrang.

Nach ärztlicher oder physiotherapeutischer Freigabe kann der frühere
Trainingsfokus mit `KNEE_REHAB_ACTIVE=false` in `.env` wieder aktiviert werden.

## ChatGPT / Codex-Automation (empfohlen)

Der tägliche Datenabruf ist von Telegram und vom OpenAI Platform API Key
entkoppelt. Die Codex-Automation startet stattdessen diesen Befehl und
verwendet die JSON-Ausgabe als Kontext für das Coaching im Chat:

```bash
./.venv/bin/python health_report.py --report morning --pretty
```

Benötigt werden weiterhin nur die Zugangsdaten für Garmin, Renpho und optional
Google Fit in `.env`. `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN` und
`TELEGRAM_CHAT_ID` sind hierfür nicht erforderlich.

Der bestehende Telegram-Bot bleibt während der Umstellung unverändert nutzbar.
Er kann erst abgeschaltet werden, wenn die ChatGPT-Automation erfolgreich läuft.

Für den Abend-Check-in wird derselbe Datenabruf mit der heutigen
Aktivitätsliste verwendet:

```bash
./.venv/bin/python health_report.py --report evening --pretty
```

## Bisheriger Telegram-Bot

### Home-Assistant-Add-on

Das Add-on liegt im Ordner `dimi_health_assistant/`. Nach dem Aktualisieren
des Add-on-Repositories in Home Assistant die Version 1.0.33 installieren oder
aktualisieren und in der Konfiguration mindestens `openai_api_key` und
`openai_model: gpt-5.6-terra` setzen.

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

Falls Google Fit keine Schritte liefert und im Log `invalid_grant` steht, ist der
gespeicherte Token abgelaufen oder widerrufen. Dann neu autorisieren:

```bash
GOOGLE_FIT_INTERACTIVE_AUTH=1 ./.venv/bin/python - <<'PY'
import asyncio
from datetime import date
from config import settings
from connectors.google_fit import get_steps

asyncio.run(get_steps(
    settings.google_client_id,
    settings.google_client_secret,
    settings.data_dir,
    date.today(),
))
PY
```

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
| `/plan` | Readiness-basierter Gesundheitsfokus für heute |
| `/erholung` | HRV, Body Battery, Training Readiness |
| `/training` | Letzte 5 Aktivitäten |
| `/woche` | Wöchentliche Zusammenfassung |
| `/gewicht` | Renpho Körperkomposition & 30-Tage-Trend |
| `/experiment_start` | 14-Tage-Experiment starten |
| `/experimente` | Aktive Experimente anzeigen |
| `/tipps` | Personalisierter Gesundheitstipp |
| `/status` | Schnellübersicht |

Experiment-Beispiel:

```text
/experiment_start Koffein vor 12 | Schlaf wird stabiler | Schlafqualität
```

## Automatische Nachrichten

| Zeit | Inhalt |
|------|--------|
| 07:30 Mo-Fr, 08:30 Sa-So | Morgen-Briefing (Schlaf, HRV, Empfehlung) |
| 20:30 täglich | Abend-Zusammenfassung (Schritte, Workouts) |
| Sonntag 18:00 | Wochen-Review mit GPT-4o |
| 07:30 (konditional) | Renpho-Erinnerung wenn >5 Tage keine Messung |

## Datenquellen & Deduplication

- **Garmin** (primär): Alle Aktivitäten, Schlaf, HRV, Body Battery, Schritte
- **Renpho** (Körperdaten): Gewicht, Körperfett, Muskelmasse — gecacht in SQLite
- **Google Fit** (Fallback): Nur Schritte wenn Garmin nicht getragen wurde

Garmin-Schritte haben immer Priorität. Google Fit wird nur genutzt wenn
Garmin < 500 Schritte für den Tag meldet (= Uhr nicht getragen).

## Aussagekräftige Statistiken

Der Bot berechnet zusätzlich eigene Coaching-Metriken:

- **Readiness Score (0–100)** aus Schlaf, HRV, Body Battery, Stress, Garmin Training Readiness und aktueller Trainingslast
- **Activity Load** pro Training aus Herzfrequenz-Zonen, Training Effect oder Puls-/Dauer-Fallback
- **Fitness / Fatigue / Form** als Trendmodell aus Trainingslast
- **Sleep Debt** gegen dein konfiguriertes Schlafziel
- **Körpertrend** mit 7-Tage-Schnitt, Wochenrate und Messqualität
- **Experimente** als 14-Tage-Interventionen mit Hypothese und Zielmetrik
- **Langzeitmarker** wie VO₂max, Fitnessalter, Ausdauerwert, Trainingsstatus,
  Atemfrequenz und SpO₂: im Wochenbericht bzw. nur bei bestätigten Änderungen,
  nicht als tägliche Trainingsziele

Diese Werte steuern `/plan`, `/heute`, `/training`, `/woche`, `/gewicht` und `/status`.

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
