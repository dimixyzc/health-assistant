# Health Assistant — Garmin, Renpho & ChatGPT Coach

Persönlicher Gesundheitsassistent für Garmin, Renpho & Google Fit.

## Tokenarmer Betrieb ab 1.1.1

- Quellenkontext: höchstens zwei lokal ausgewählte Auszüge mit je maximal
  850 Zeichen; gesamter Quellen-JSON-Kontext höchstens 3.200 Zeichen
  (vorher 9.000). Kapitelreferenzen bleiben erhalten.
- Frühere Coachingtexte: zwei lokale Auszüge mit insgesamt höchstens
  725 Zeichen statt mehrerer vollständiger Nachrichten. Keine zusätzliche
  KI-Anfrage für Zusammenfassungen oder Buchsuche.
- Kürzere gemeinsame Regeln; bei gezielten freien Fragen nur relevante
  Körper-/Aktivitätsdaten. Fragen und darin genannte Beschwerden werden
  nicht abgeschnitten.
- Ausgabegrenzen: 450 Tokens für Routine-Coaching, 650 für Wochenreviews,
  750 für freie Fragen. GPT-6 Luna läuft weiterhin ohne Reasoning-Tokens.
- Logs zeigen tatsächliche Eingabe-, Ausgabe-, Reasoning- und gecachte
  Eingabetokens, ohne Gesundheits- oder Buchtexte zu protokollieren.
- Der JSON-Bericht lässt leere Werte und doppelte Langzeitwerte weg;
  echte Nullwerte und `false` bleiben erhalten.

Ein lokaler Vergleich von sieben synthetischen Anfragen mit identischen
Daten und derselben Buchquelle ergab gegenüber 1.1.0 etwa **53–64 % weniger
Eingabetokens** (Schätzung mit `o200k_base`, ohne Nachrichten-Overhead).
Das ist keine Messung der API-Abrechnung. Tatsächlicher Verbrauch und mögliche
Cache-Treffer hängen von der Anfrage ab; die API-Nutzungslogs sind maßgeblich.
Reha-, Medikamenten- und Quellenregeln bleiben erhalten. Es werden keine
Gesundheitsantworten wiederverwendet, die auf veralteten Messwerten beruhen.

## Neu in 1.1.0: Huberman als persönliche Wissensquelle

Der Coach berücksichtigt Andrew Hubermans *Protocols: An Operating Manual for
the Human Body* bei Morgen-/Abendbriefings, Wochenreviews, Körperdaten,
Gesundheitsfokus, Tipps und freien Fragen. Er sucht lokal passende Kapitel und
Protokolle und übergibt bis zu zwei kurze Auszüge an GPT-6 Luna. Deutsche
Suchbegriffe werden um englische Themenbegriffe ergänzt. Der tägliche
`health_report.py` enthält ebenfalls Buchkontext und Coaching-Regeln.

Die Buchquelle ergänzt persönliche Messdaten, allgemeines Gesundheitswissen und
hinterlegte, am 08.11.2026 geprüfte Hinweise von
[CDC zum Schlaf](https://www.cdc.gov/sleep/about/),
[WHO zur Ernährung](https://www.who.int/news-room/fact-sheets/detail/healthy-diet) und
[NIH zu Nahrungsergänzung](https://ods.od.nih.gov/factsheets/WYNTK-Consumer/).
Es gibt keine Live-Literatursuche. Buchprotokolle sind keine medizinischen
Leitlinien; individuelle Behandlung und Reha haben Vorrang. Empfehlungen sollen
passende Buchprotokolle benennen, Unsicherheit deutlich machen und höchstens
1–2 alltagstaugliche Prioritäten setzen. Der Coach übernimmt keine
Trainingsziele oder Supplement-Dosierungspläne aus dem Buch.

### Buch in Home Assistant hinterlegen

1. Deine EPUB-Datei einmalig als
   `/share/health-assistant/huberman_protocols.epub` auf dem Home-Assistant-Gerät
   ablegen (Ordner gegebenenfalls erstellen, z.B. über die Samba-Freigabe).
2. Add-on-Repository aktualisieren, **Dimi Health Assistant 1.1.1** installieren
   und starten. Das Buch wird lokal eingelesen; der Index liegt persistent unter
   `/data/knowledge/`. Auch eine später abgelegte Datei wird erkannt.
3. Mit `/wissen` prüfen, ob das Buch geladen wurde und welches Modell läuft.

Alternativ `knowledge_book_path` auf einen anderen im Add-on erreichbaren
EPUB-Pfad setzen. Ohne diese Option wird zuerst
`/data/knowledge/huberman_protocols.epub`, danach der obige `/share`-Pfad geprüft.
Fehlt die Datei oder ist sie ungültig, bleibt der Coach ohne Buchstellen nutzbar
und behauptet keinen Buchzugriff. Bei expliziten Buchfragen benennt er die Lücke.

**Wichtig beim Update:** Home Assistant behält gespeicherte Optionen bei.
Die früheren Standardmodelle `gpt-4o`, `gpt-5.5` und `gpt-5.6-terra` werden beim
Start auf `gpt-6-luna` umgestellt. Andere ausdrücklich konfigurierte Modelle
bleiben erhalten. Für eine eindeutige Anzeige in der Add-on-Konfiguration
`openai_model: gpt-6-luna` speichern. Dein API-Key muss Zugriff auf dieses Modell
haben; es gibt keinen stillen Wechsel auf ein anderes Modell.

### Buch lokal oder für Docker importieren

```bash
./.venv/bin/python -m knowledge.import_epub "/pfad/zum/buch.epub" --data-dir ./data
```

Der Import speichert eine private Kopie und einen lokalen Suchindex. Der
bestehende Docker-Compose-Datenmount stellt sie unter `/data/knowledge` bereit.
Für lokale Aufrufe `DATA_DIR=./data` setzen oder `KNOWLEDGE_BOOK_PATH` auf die
importierte EPUB setzen. Der Import benötigt weder API-Key noch Cloud-Upload.
Nur die ausgewählten Auszüge werden zusammen mit dem Coaching-Kontext an
OpenAI übertragen. EPUB und Index bleiben aus Git und Docker-Images ausgeschlossen.

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
des Add-on-Repositories in Home Assistant die Version 1.1.1 installieren oder
aktualisieren und in der Konfiguration mindestens `openai_api_key` und
`openai_model: gpt-6-luna` setzen.

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
| `/wissen` | Status der Buchquelle und des verwendeten Modells |

Experiment-Beispiel:

```text
/experiment_start Koffein vor 12 | Schlaf wird stabiler | Schlafqualität
```

## Automatische Nachrichten

| Zeit | Inhalt |
|------|--------|
| 07:30 Mo-Fr, 08:30 Sa-So | Morgen-Briefing (Schlaf, HRV, Empfehlung) |
| 20:30 täglich | Abend-Zusammenfassung (Schritte, Workouts) |
| Sonntag 18:00 | Wochen-Review mit GPT-6 Luna |
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
├── ai/              # OpenAI GPT-6 Luna Client
├── knowledge/       # Lokale EPUB-Suche, Quellen und Coaching-Regeln
├── bot/             # aiogram Handlers + APScheduler
├── storage/         # SQLite Datenbank
└── data/            # Persistente Daten (gitignored)
```
