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
