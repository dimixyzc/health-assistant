# Momentum aktualisieren

Privates Dashboard für Dimitri. Aktualisierung ausschließlich auf Anfrage ("Daten ziehen"), keine automatische Routine.

1. Im gemeinsamen Health-Assistant-Projekt die lokale virtuelle Python-Umgebung verwenden und `sites/momentum/refresh_data.py` ausführen. Sie nutzt die gemeinsamen Garmin-/Renpho-Zugänge und den lesenden Trainingskalender und ersetzt `dist/data.json` atomar. Keine Zugangsdaten, Tokens, GPS-Spuren oder Kontoprofile in die Site aufnehmen.
2. Datenprüfung: fehlende Werte nicht ersetzen; bei Fehlern zurückbehaltene Renpho-Werte und deren Datum beachten. Kraftlasten von Maschinen nicht ohne passende Geräteinformationen vergleichen; fehlende/0-kg-Squatlasten nicht als bestätigte Leistung werten.
3. Bestehende Site aus `.openai/hosting.json` verwenden, neue Schreibberechtigung über Sites abrufen. Gemäß Sites-Skill die Änderungen mit dem Source-Helper pushen und privat veröffentlichen. Kein neues Projekt erstellen. Notes liegen nur im Browser und bleiben bei Datenupdates erhalten.
4. Veröffentlichungsstatus prüfen und Datenstand im Chat nennen. Niemals den Garmin-Kalender im Rahmen eines Datenupdates ändern.

Momentum ist die Planerfüllung bis zum Datenstichtag, kein medizinischer oder Leistungs-Score. Ruhetage zählen nicht als Ausfall. Bei expliziten Änderungen des Trainingsplans dessen veröffentlichte Kalenderdaten aktualisieren.
