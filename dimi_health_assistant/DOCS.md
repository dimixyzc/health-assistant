# Dimi Health Assistant 1.1.0

## Einrichtung

Telegram-, Garmin- und Renpho-Zugangsdaten sowie `openai_api_key` konfigurieren.
Das Modell ist `gpt-6-luna`. Bei Updates werden frühere Standardmodelle
(`gpt-4o`, `gpt-5.5`, `gpt-5.6-terra`) beim Start migriert. Für eine passende
Anzeige der gespeicherten Konfiguration `openai_model: gpt-6-luna` speichern.

## Hubermans Buch hinterlegen

Die persönliche EPUB-Kopie unter diesem Pfad auf dem Home-Assistant-Gerät
ablegen, beispielsweise über die Samba-Freigabe:

```text
/share/health-assistant/huberman_protocols.epub
```

Den Ordner `health-assistant` bei Bedarf anlegen. Das Add-on liest die Datei
automatisch und speichert den Suchindex unter `/data/knowledge/`. Die Datei
kann auch nach dem Start abgelegt werden. Mit `/wissen` in Telegram lassen sich
Buchstatus und Modell prüfen. Alternativ `knowledge_book_path` auf einen
anderen im Add-on erreichbaren EPUB-Pfad setzen.

Die EPUB ist nicht Bestandteil des öffentlichen Add-ons. Nur passende kurze
Auszüge werden mit der jeweiligen Anfrage an OpenAI gesendet. Die Datei und der
Index bleiben lokal. Ohne gültige EPUB arbeitet der Coach ohne Buchbezug weiter.

## Empfehlungen

Das Buch dient als wichtige zusätzliche Quelle. Persönliche Gesundheitsdaten,
allgemeines Gesundheitswissen und hinterlegte CDC-/WHO-/NIH-Hinweise ergänzen es.
Es erfolgt keine Live-Literatursuche. Der individuelle Behandlungsplan und die
Knie-Reha haben Vorrang; Trainingsziele und Supplement-Dosierungspläne werden
nicht aus dem Buch übernommen. Quellenmaterial wird als Referenztext behandelt,
nicht als Anweisung an den Assistenten.

`/hilfe` zeigt alle Befehle, `/wissen` den Quellenstatus.
