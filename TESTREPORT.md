# Prüfung · 18. Oktober 2026 · Version 0.3.0

- Python **3.14.4**, Home Assistant Core **2026.10.2**
- ZHA **2.3.1**, zha-quirks **2.3.0**, zigpy **2.3.0**
- **78 Tests bestanden**, fünf Deprecation-Warnungen aus HA und backoff.
- Echte HA-Klassen und zigpy-ZCL-Serializer, simuliertes entferntes Gerät.

Die Suite prüft jetzt den reinen Schreibmodus. Die bisherigen Tests der
entfernten RPC-Lesewege und Diagnoseoberflächen wurden durch Tests der
neuen Abläufe ersetzt; die Testanzahl ist deshalb nicht mit 0.2.3 vergleichbar.

Geprüft:

- Gebundene Zigbee-Schreibtransaktionen, Profil/Hersteller/Endpunkt/Sequenz,
  reguläre und Default Responses mit/ohne Herstellerkopf, explizite
  Schreibfehler, fehlende Bestätigung vor/nach vollständiger Anfrage,
  Aufräumen nach Abbruch und keine automatische Wiederholung.
- Alle Betriebsabläufe ausschließlich mit ZCL Write Attributes: kein GetConfig,
  GetStatus oder Lesen der RPC-Mailbox, auch nicht beim Abbrechen/Wiederherstellen.
- Erster Mindestwertversuch startet bei 0, verändert nur range_map und lässt
  Gamma unangetastet. Gamma startet beim gespeicherten bzw. konfigurierten Wert,
  verändert nur Gamma und lässt die Grenzen unangetastet.
- Erster Abbruch ohne Rücksetzwert sendet keinen erfundenen ursprünglichen Wert;
  zuletzt gesendete Testwerte können im simulierten Gerät bleiben. Sie werden
  dabei nicht als gespeicherte HA-Werte übernommen. Die Lichtanforderung wird
  wiederhergestellt. Ein späterer Abbruch sendet nur den zuvor gespeicherten
  Parameter erneut. Externe Geräteeinstellungen werden nicht zurückgelesen.
- Speichern sendet den Parameter nochmals und hält lokale Werte erst nach
  erfolgreicher lokaler Speicherung vor. Getrennte Werte für Grenzen und Gamma,
  lokale Persistenz über Neuladen ohne Gerätezugriff, Obergrenze/Startgamma und
  die Grenzen der Eingabewerte.
- Ein simulierter RPC-Fehler bei gleichzeitig bestätigten ZCL-Schreibzugriffen
  wird ausdrücklich NICHT als bestätigter Gerätewert dargestellt. Das zeigt
  die verbleibende Grenze des Schreibmodus auch bei grünen Tests.
- Sicherung vor erster Geräteänderung, fehlgeschlagene lokale Speicherung,
  Erhalt eines offenen Abschlusses, Rücksetzung nach erneutem Erreichbarwerden,
  Abschluss ohne bekannten Rücksetzwert, Migration eines alten nativen Journals,
  Schutz vor einer Wiederherstellung auf einer anderen Licht-Entität.
- Auf- und Abwärtsvorschau, Grenzwerte, Timeout, Save/Cancel, gegenseitige Sperren
  mit automatischer Kalibrierung, stale Sitzungskennungen, Fehler und Unload.
- Gerätebedienung am bestehenden ZHA-Gerät mit eindeutigen Kennungen, bewahrte
  Kalibrierungsbutton-Migration und aktuelle Registry-API. Cleanup beider alter
  RPC-Probes mit echten HA-Registries: wiederholbar, auf den eigenen
  Konfigurationseintrag begrenzt, Licht und Gerät bleiben bestehen.
- Der vereinfachte Optionsdialog ändert nur Startwerte, startet keinen Versuch
  und ist während laufender Versuche gesperrt. Status und exportierte Diagnose
  kennzeichnen lokale/gesendete Werte ausdrücklich als unbestätigt.

Nicht geprüft: Tatsächliche Annahme, Wirkung oder Persistenz von gamma/range_map
auf einem physischen Shelly Dimmer Gen4 mit 2.0.1, Funkübertragung am Sonoff MG24,
visueller Verlauf der Philips-Lampe, Browserdarstellung auf dem Green und
vollständiger Core-Start auf Home Assistant OS. Die Wirkung muss bei der ersten
Verwendung an der Lampe geprüft werden. Das Update behebt das Firmware-Leseproblem
nicht; es umgeht die Abhängigkeit davon.
