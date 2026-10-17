# Prüfung · 17. Oktober 2026

- Home Assistant Core: **2026.10.2**, Python 3.14.4
- ZHA: **2.3.1**, zha-quirks: **2.3.0**, zigpy: **2.3.0**
- **38 Tests bestanden**, keine fehlgeschlagenen Tests.
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
