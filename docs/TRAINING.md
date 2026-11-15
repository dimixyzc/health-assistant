# Gemeinsamer Health Assistant und Trainingskontext

Ein Repository betreibt Gesundheitscoaching und lesendes Trainingswissen. Workouts werden weiterhin über Codex geplant und bei gesondertem Auftrag in Garmin geändert. Telegram erstellt, verschiebt oder veröffentlicht keine Workouts.

## Telegram und Kalender

`/plan` zeigt heute und am nächsten terminierten Tag alle vorhandenen Garmin-Workouts mit verfügbaren Schritten. Dieser Befehl benötigt keine KI. Trainingsfragen sowie bestehende Tages- und Wochenberichte können kurze Kalenderzusammenfassungen verwenden. Ein lokaler Planentwurf gilt niemals als terminierter Garmin-Eintrag. Eine absolvierte Aktivität wird nur bei expliziter Workout-Verknüpfung und passendem Datum zugeordnet.

Der Kalender umfasst sieben Tage Vergangenheit und 14 Tage Zukunft. Ein lokaler Cache ist 15 Minuten gültig. Bei Garmin-Ausfällen erscheint der letzte erfolgreiche Stand mit Datum; ohne Cache wird fehlende Verfügbarkeit angezeigt. Fehlende Termine bedeuten nicht automatisch Ruhetage. Kalender- und Detailabrufe haben begrenzte Laufzeiten, Detailausfälle lassen den verfügbaren Kalender bestehen.

## Lokale Codex-Planung

Installation: `python -m pip install -e '.[dev]'`. Die bestehende `training-plan`-CLI behält ihre Befehle `import`, `week-analysis`, `preview`, `dry-run` und `feedback`. `publish` bleibt gesperrt. Die Migration aktiviert keine automatischen Änderungen oder Belastungssteigerungen.

Der Planer nutzt die gemeinsamen Garmin-Zugänge und den Token-Cache unter `DATA_DIR/.garminconnect`. Die Trainingsdatenbank liegt separat unter `DATA_DIR/training/training_plan.sqlite3`. `TRAINING_DATA_DIR` kann den Datenpfad ausdrücklich überschreiben. Die Importhistorie, das Sync-Register und vorhandenes Feedback bleiben erhalten. Der Datenimport erfolgt weiter auf Anfrage über Codex.

Persönliche Übungsauswahl und historische Vorlagen liegen ausschließlich in `private/training/profile.json`; `TRAINING_PROFILE_PATH` überschreibt diesen Pfad. Ohne Profil erzeugt der lokale Planer keine vermeintlich persönlichen Vorgaben. Quellen und persönliche Projektnotizen liegen unter `private/references` bzw. `private/training`. Öffentliche Tests verwenden ausschließlich synthetische Profile.

## Momentum

`python sites/momentum/export_data.py` aktualisiert den bestehenden privaten Snapshot auf Anfrage. Kalenderzugriff und Garmin-Anmeldung werden mit dem Bot geteilt. Der Export erhält vorhandene Werte bei Ausfällen und schreibt entsprechende Warnungen. Quelldaten, generierte `dist/data.json` und Hosting-Zuordnungen unter `.openai` gehören nicht in Git oder das Add-on-Image. Die bestehende veröffentlichte Site und deren lokale Browsernotizen werden durch einen lokalen Export nicht verändert.

## Betrieb und Entwicklung

`python tools/sync_addon.py` kopiert ausschließlich freigegebene Python-Laufzeitmodule in den Add-on-Buildkontext. Private Dateien und Dashboard-Snapshots sind ausgeschlossen. `python -m pytest -q` führt beide zusammengeführten Testsammlungen aus. Der vorhandene Unittest-Aufruf bleibt für die Health-Assistant-Tests verfügbar.

Eine einmalige private Migration kann die Trainingsdatenbank und das Profil unter `/share/health-assistant/training-seed/` bereitstellen. Das Add-on übernimmt diese Dateien nur, wenn das jeweilige Ziel unter `/data/training/` noch nicht existiert. Vorhandene Laufzeitdaten werden nie überschrieben. Der Telegram-Kalenderzugriff funktioniert auch ohne lokales Planungsprofil.

Vor einer Migration beide Arbeitsverzeichnisse und das laufende Add-on sichern. Private Daten mit Prüfsummen bzw. SQLite-Backup übernehmen; abweichende vorhandene Zieldateien nicht überschreiben. `training_plan.migration.migrate_files` prüft Konflikte vor dem Kopieren und lässt identische Wiederholungen zu. Der alte Projektpfad kann nach erfolgreicher Prüfung als Kompatibilitätslink auf das gemeinsame Projekt bestehen bleiben.
