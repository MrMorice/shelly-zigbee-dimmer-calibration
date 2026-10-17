# Prüfung · 17. Oktober 2026

- Home Assistant Core: **2026.10.2**, Python 3.14.4
- ZHA: **2.3.1**, zha-quirks: **2.3.0**, zigpy: **2.3.0**
- **80 Tests bestanden**, keine fehlgeschlagenen Tests.
- Fünf Deprecation-Warnungen stammen aus Home Assistant und backoff.

Geprüft wurden Zigbee-Nachrichten mit echten zigpy-ZCL-Serialisierern,
mehrteilige RPC-Antworten, alte Antworten in der Mailbox, Shelly-Fehler,
abgelehnte Schreibzugriffe, verlorene Antworten vor/nach dem Start,
Abbruch und Aufräumen des Listeners, Zuordnung zum richtigen Gerät,
ungültige Antworten, Modell-/Profilprüfung, Schutz vor doppeltem Start,
der Einrichtungsdialog mit echten Home-Assistant-Klassen und die
Einrichtung ohne automatische Kalibrierung.

Nicht geprüft: Funkübertragung am Sonoff MG24, Verhalten eines echten
Shelly Dimmer Gen4, erfolgreicher physischer Kalibrierungsabschluss,
vollständiger Core-Start auf Home Assistant OS und andere Core-Versionen.
Das entfernte Gerät und Teile des Einrichtungsumfelds wurden simuliert.
Der praktische Test erfolgt erst nach Installation auf dem Green.

Version 0.1.1 ergänzt den tatsächlich gemeldeten Zigbee-Modellnamen `Dimmer`.
Sieben zusätzliche Tests prüfen die Modellnamen sowie die weiterhin erforderlichen
Hersteller-, Endpunkt- und Clustermerkmale.

Version 0.1.2 ergänzt acht Tests: Schreiben ohne RPC-Lesezugriff, reguläre
Schreibantworten und Default Responses mit/ohne Herstellerkopf, explizite
ZCL-Fehler, zeitüberschrittene TxCtl-Anfrage mit Phasenangabe sowie den auf
den ZHA-Konfigurationseintrag begrenzten Registry-Aufruf. Die normale Aktion
bestätigt nur die Zigbee-Übertragung, nicht Start oder Erfolg der Kalibrierung.
Der gemeldete Hardware-Timeout wurde ohne Funkhardware nicht reproduziert;
die tatsächliche Kalibrierung muss nach dem Update erneut geprüft werden.

Version 0.1.3 ergänzt vier Tests für die Gerätezuordnung: direkte Zuordnung
des Buttons ohne DeviceInfo, Plattform-Setup am bestehenden Gerät sowie
Migration mit den echten Geräte- und Entitätsregistries von Core 2026.10.2
(mit und ohne weitere Entität am bisherigen Doppeleintrag). Die Tests prüfen
den Erhalt der Entity-ID, den unveränderten Lichtausgang, die wiederholbare
Migration und die gezielte Entfernung ausschließlich leerer eigener Duplikate.
Brand-Bilder wurden separat auf PNG-Format, Größe und deckenden Hintergrund geprüft.


Version 0.2.0 ergänzt den nativen Dimmkurven-Assistenten. Geprüft sind:

- Erkennung unterstützter `gamma`-/`range_map`-Antworten und Ablehnung ungültiger
  oder unvollständiger Gerätekonfigurationen.
- Partielle native Änderungen, unveränderte Obergrenze und unveränderte fremde
  Einstellungen; keine zusätzliche Licht-Entität und keine Software-Gammakurve.
- Mindestwertsuche, Gamma-Vorschau aufwärts/abwärts, Grenzen, explizites Speichern,
  Abbrechen, Dialogschließen und automatischer Abbruch nach fünf Minuten.
- Native Rücksetzung vor Wiederherstellung der Lampenhelligkeit, persistente
  Sicherung vor dem ersten Schreibzugriff und Erhalt bei fehlgeschlagener
  Wiederherstellung oder fehlgeschlagenem Speichern der lokalen Daten.
- Sperren bei parallelen Sitzungen, veralteten Dialogen und automatischer
  Hardwarekalibrierung.
- Tatsächliche Home-Assistant-OptionsFlow-Methoden und Auflösung der bestehenden
  ZHA-Licht-Entität mit echten Geräte-/Entitätsregistries.
- `Light.GetConfig` und `Light.SetConfig` über den realen ZCL-Serializer,
  mehrteilige RPC-Antworten, Zuordnung zur richtigen RPC-ID/Zielkennung,
  fremde Mailbox-Antworten, RPC-Fehler und keine automatische Wiederholung
  nach verlorenem Schreib-Ergebnis.
- Ablauf Start → Mindestwert ändern → Speichern → neuer Versuch → Abbrechen
  durch Runtime, Assistent und RPC-Transport mit simulierter Shelly-Mailbox.
- Firmware ohne RPC-Leseantwort: Nur `Light.GetConfig` wird angefragt;
  kein `Light.SetConfig`, kein Helligkeitsbefehl, keine Vorschau beginnt.

Nicht am physischen Gerät geprüft: Verfügbarkeit der RPC-Leseantworten dieser
Shelly-Firmware, Unterstützung der nativen Parameter auf diesem Modell,
Wirkung der nativen Kurve auf Zigbee und Wandtaster, tatsächliche Helligkeits-
und Warmtonwahrnehmung sowie Beständigkeit der Werte nach Geräte-Neustart.
Die native Vorschau schreibt Einstellungen bereits während des Versuchs.
Offline-/Stromausfall-Rücksetzung kann erst nach Wiederherstellung der Verbindung
und erneutem Öffnen des Assistenten abgeschlossen werden. Die Tests bestätigen
keine erfolgreich über Funk ausgeführte Gerätekonfiguration.


Version 0.2.1 ergänzt sieben Tests für die Gerätebedienung: Alle acht Entitäten
(automatischer Kalibrierungsbutton, sechs Assistentenknöpfe und Statussensor)
verweisen auf denselben bestehenden ZHA-Geräteeintrag und verwenden keine
neue DeviceInfo. Geprüft sind Mindestwertsuche und Speichern, native
Gamma-Anpassungen und Abbruch, Rücksetzung nach fehlgeschlagener Anpassung,
Wiederherstellung einer unterbrochenen Sitzung ohne neue Vorschau,
Statusaktualisierung nach Freigabe der Sitzungssperre und Schutz eines
laufenden Versuchs vor einem zweiten Start. Die Einordnung in den Bereich
Konfiguration wird über EntityCategory.CONFIG vorgegeben; ein visueller Test
im Browser des Green wurde nicht durchgeführt.
