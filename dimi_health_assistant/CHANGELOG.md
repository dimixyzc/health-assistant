# 1.2.0

- Gemeinsames Projekt für Gesundheitscoaching, lokale Codex-Trainingsplanung und Momentum.
- `/plan` zeigt die heutige und nächste in Garmin terminierte Einheit, ohne KI-Aufruf.
- Trainingsfragen und Berichte berücksichtigen einen begrenzten, lesenden Kalenderkontext mit Datenstand.
- Kalender-Cache mit 15 Minuten Gültigkeit, Ausfallanzeige und Unterstützung mehrerer Einheiten pro Tag; lokale Entwürfe werden nie als Garmin-Termine ausgegeben.
- Planen, Veröffentlichen und Ändern von Workouts bleiben Aufgaben für Codex; Telegram hat keinen Schreibpfad.
- Persönliche Profile, Trainingsdaten, Bücher und Hosting-Zuordnungen bleiben außerhalb von Git und Image.

# 1.1.6

- Freitext erkennt Workout-Fragen und nutzt vorhandene Aktivitäten; kurze Rückfragen behalten bis zu zwei Gesprächsschritte für maximal eine Stunde im Arbeitsspeicher.
- Antworten ersetzen die Warte-Nachricht. Sichere HTML-Formatierung, Absätze und Aufteilung langer Texte verbessern die mobile Lesbarkeit.
- Technische Fehler, Zeitüberschreitungen, unbekannte Befehle und nicht unterstützte Medien erhalten eine verständliche Rückmeldung.
- OpenAI-Aufrufe haben feste Zeitlimits und höchstens zwei Wiederholungen bei temporären Modellfreigabefehlern; kein Modellwechsel.
- Trainingswerte sind gerundet, doppelte Handy-Quellen entfernt und unbekannte Renpho-Messhistorie wird nicht mehr als 999 Tage ausgegeben.
- Fehlerlogs enthalten nur Fehlerklassen statt möglicherweise privater Antwortinhalte.

# 1.1.5

- Deutsche Fragen und zusammengesetzte Begriffe finden passende englische Buchstellen zuverlässiger.
- Morgen- und Abendberichte nutzen wechselnde, kontextbezogene Buchstellen und können passende Wissensimpulse mit Quellenangabe einstreuen.

# 1.1.4

- Kurzzeitige GPT-6-Luna-Freigabefehler werden begrenzt erneut versucht.

# 1.1.3

- Garmin-Anmeldepause wird in `/data` gespeichert und bleibt bei Neustarts
  bestehen, damit ein Neustart keine neue Login-Welle auslöst.
- Versionsanzeige im Add-on-Log auf 1.1.3 aktualisiert.

# 1.1.2

- Garmin-Anmeldungen laufen nur noch einmal gleichzeitig; parallele Aufrufe
  starten keine neuen Login-Wellen.
- Nach 45 Sekunden gibt der Bot eine verständliche Rückmeldung zurück und
  pausiert weitere Garmin-Login-Versuche für 15 Minuten.
- `/heute` liefert weiterhin die verfügbaren Daten und kennzeichnet Garmin
  separat als vorübergehend nicht erreichbar.

# 1.1.1

- Tokenarmer Quellenkontext: zwei Auszüge mit je höchstens 850 Zeichen,
  insgesamt maximal 3.200 Zeichen inklusive ergänzender Quellen.
- Kürzere gemeinsame Coaching-Regeln und auf 725 Zeichen begrenzte Historie.
- Bei gezielten Fragen keine fachfremden Körper- und Aktivitätsdaten senden.
- Ausgabelimits nach Aufgabe: 450/650/750 Tokens; GPT-6 Luna ohne Reasoning.
- Tatsächliche gecachte Eingabetokens zusätzlich in den Nutzungslogs.
- JSON-Berichte ohne leere Felder und doppelte Langzeitwerte.
- Lokaler Vergleich mit sieben synthetischen Anfragen: geschätzt 53–64 % weniger
  Eingabetokens als 1.1.0 (o200k_base, ohne Nachrichten-Overhead; keine Live-API-Messung).
- Reha-, Medikamenten- und Quellenregeln bleiben erhalten.

# 1.1.0

- GPT-6 Luna als Standardmodell für alle Coaching-Antworten; bisherige
  Standardmodelle werden beim Add-on-Start migriert.
- Hubermans „Protocols“ als private, lokal durchsuchbare EPUB-Wissensquelle.
  Die persönliche Datei unter `/share/health-assistant/huberman_protocols.epub`
  ablegen. Buch und Suchindex sind nicht im öffentlichen Repository enthalten.
- Passende Buchauszüge mit Kapitel-/Protokollreferenzen für Briefings,
  Wochenreviews, Körperdaten, Gesundheitsfokus, Tipps und freie Fragen.
- Ergänzende CDC-/WHO-/NIH-Hinweise; klare Trennung von Messdaten,
  Buchvorschlägen, allgemeinem Wissen und unsicherer Evidenz.
- Individueller Behandlungsplan und Knie-Reha haben Vorrang vor Buchprotokollen.
- Neuer Telegram-Befehl `/wissen` zeigt Buchstatus und Modell an.
- Bei fehlendem Buch oder einer ungültigen EPUB bleibt der Coach nutzbar,
  ohne Buchzugriff vorzutäuschen.
- Private Daten und Buchdateien werden aus Docker-Build-Kontexten ausgeschlossen.
