# Shelly Zigbee Calibration · 0.3.0

<img src="https://raw.githubusercontent.com/MrMorice/shelly-zigbee-dimmer-calibration/main/custom_components/shelly_zigbee_calibration/brand/icon%402x.png" alt="Frontaler 3D-Dimmer mit hellem Hintergrund" width="128">

Mindesthelligkeit und Gamma direkt am **Shelly Dimmer Gen4** einstellen,
ausschließlich über die vorhandene **ZHA-/Zigbee-Verbindung**. WLAN, Cloud,
MQTT, ZHA Toolkit und ein weiterer Funkstick werden nicht benötigt.
Die Bedienelemente gehören zum **vorhandenen Shelly-Gerät**; es entsteht
keine zweite Licht-Entität und kein zusätzlicher Dimmer.

Ab **0.3.0** arbeitet der Assistent **nur schreibend**. Er benötigt weder
`Light.GetConfig` noch eine lesbare RPC-Antwort. Die Einstellungen werden
im Shelly ausprobiert; du beurteilst die Wirkung direkt an der Lampe.
Eine bestätigte Zigbee-Übertragung beweist nicht, dass die Shelly-Firmware
den Parameter angenommen oder dauerhaft gespeichert hat. Home Assistant
speichert deshalb **zuletzt gesendete Werte**, keine zurückgelesenen Gerätewerte.

## Update auf 0.3.0

1. In HACS die Integration aktualisieren. Wenn kein Update erscheint, über
   das HACS-Menü erneut herunterladen und `main` auswählen.
2. Home Assistant **neu starten**; ein Neuladen der Integration reicht zum
   Austausch aller Python-Dateien nicht aus.
3. **Einstellungen → Geräte & Dienste → Geräte → deinen vorhandenen Shelly**
   öffnen. Die Knöpfe stehen unter **Konfiguration**.

Die beiden bisherigen Knöpfe „Zigbee-RPC prüfen“ und „Zigbee-RPC kurz prüfen“
werden beim Setup gezielt aus dem Entitätsregister entfernt. Der alte
RPC-Diagnosebericht und die nicht mehr benötigten Lesewege wurden entfernt.
Der zusätzliche Assistent im Integrationsdialog entfällt ebenfalls; dort
lassen sich nur noch optionale Startwerte einstellen. Vorhandene Bedienknöpfe
und der Statussensor behalten ihre eindeutigen Kennungen und Entity-IDs.
Der automatische Kalibrierungsbutton heißt jetzt zur Unterscheidung
**Automatische Kalibrierung starten**.

## Mindesthelligkeit finden

1. **Mindesthelligkeit suchen** drücken. Die native Untergrenze beginnt bei
   **0 %**. Die Lampe wird anschließend mit ungefähr **1 %** Helligkeit
   angefordert (ZHA quantisiert die Helligkeit auf Zigbee-Stufen).
2. **Dimmwert erhöhen (+)** erhöht die native Untergrenze um **0,5 %**.
   Wiederholt drücken, bis die Lampe zuverlässig leuchtet.
3. **Dimmwert senken (−)** reduziert den Wert bei Bedarf wieder um 0,5 %.
4. **Dimmwerte speichern** sendet den Wert erneut und speichert ihn in HA.

Dabei wird ausschließlich `range_map` verändert. Gamma bleibt unangetastet.
Die Unter- und Obergrenze müssen zusammen gesendet werden: Die Obergrenze
ist beim ersten Versuch standardmäßig **100 %**. Eine möglicherweise
abweichende bisherige Obergrenze des Shelly kann nicht automatisch erkannt
werden. Nach einer gespeicherten Mindestwertsuche wird deren Obergrenze
weiterverwendet, sofern kein anderer Startwert konfiguriert ist.

## Gamma einstellen

1. **Gamma-Vorschau starten** drücken. Der zuletzt in HA gespeicherte
   Gamma-Wert wird gesendet; beim ersten Versuch beginnt Gamma bei **1,0**.
2. Die Lampe fährt wiederholt von dunkel nach hell und zurück. Ein Zyklus
   dauert ungefähr **25 Sekunden zuzüglich Zigbee-Übertragungszeit**.
3. **Dimmwert erhöhen (+)** erhöht Gamma um **0,1**,
   **Dimmwert senken (−)** reduziert Gamma um 0,1.
4. Vergleiche die Gleichmäßigkeit des Verlaufs und drücke
   **Dimmwerte speichern**, wenn er passt.

Dabei wird ausschließlich `gamma` geschrieben. Mindest- und Obergrenze
bleiben unangetastet. Gamma ist auf den dokumentierten Bereich **0,4–4,0**
begrenzt. Die Software bildet keine eigene Helligkeitskurve nach.
Bei einer anderen Lampe die Einstellungen erneut visuell prüfen.

## Speichern, Abbrechen und Unterbrechungen

**Speichern:** Den aktuellen Parameter erneut senden, den vorher von ZHA
gemeldeten Ein-/Aus-Zustand und bei eingeschalteter Lampe die vorherige
Helligkeitsanforderung wiederherstellen, anschließend den Parameter lokal
in HA speichern. Bei geänderter Kurve kann dieselbe Helligkeitsanforderung
natürlich anders aussehen. Ein Mindestwertversuch speichert nur die Grenzen,
ein Gamma-Versuch nur Gamma. Erst ausdrücklich gespeicherte Werte dienen
als Rücksetzwerte für weitere Versuche desselben Parameters.

**Abbrechen:** Die Vorschau stoppen. Falls der betreffende Parameter bereits
in HA gespeichert war, diesen erneut senden. Anschließend die vorherige
Lichtanforderung wiederherstellen. Die tatsächliche Übernahme im Shelly kann
auch dabei nicht bestätigt werden.

**Erster Versuch ohne gespeicherten Rücksetzwert:** Die bisherigen Gerätewerte
sind unbekannt. Abbrechen stoppt die Vorschau und stellt die Lichtanforderung
wieder her, kann aber die ursprüngliche Geräteeinstellung nicht zurücksetzen.
Der zuletzt gesendete Testwert kann im Shelly bleiben. Er wird dabei **nicht**
als gespeicherter HA-Rücksetzwert übernommen. Das gilt unabhängig für
Mindesthelligkeit und Gamma. Ein in HA gespeicherter anderer Parameter wird
beim Abbrechen nicht überschrieben.

Nach **fünf Minuten** wird automatisch abgebrochen, mit denselben Regeln.
Vor der ersten Geräteänderung wird der bekannte Rücksetzwert (falls vorhanden)
zusammen mit dem vorherigen Lichtzustand in HA gesichert. Bei Offline-Zustand,
Stromausfall oder fehlgeschlagenem Speichern kann ein Abschluss offenbleiben.
Dann den Shelly wieder erreichbar machen und **Dimmversuch abbrechen** drücken.
Die Sicherung bleibt bis zum erfolgreichen Abschluss erhalten. Beim ersten
Versuch ohne Rücksetzwert werden dabei nur die Lichtanforderungen wiederhergestellt.
Auch das Starten eines weiteren Versuchs erledigt zuerst einen offenen Abschluss.
Ein Core-Neustart allein verändert weder die Lampe noch die Dimmwerte.

Während eines Versuchs keine weiteren Automationen, Taster oder RPC-Clients
verwenden, die dieselbe Lampe oder ihre Einstellungen verändern.
Die Integration sperrt nur ihre eigenen parallelen Vorgänge.

## Anzeige und optionale Startwerte

**Dimmkurven-Status** zeigt den laufenden Wert und danach beispielsweise:

- „Werte gesendet und in HA gespeichert“
- „Gespeicherte Werte erneut gesendet“
- „Gestoppt – vorherige Gerätewerte unbekannt“
- „Wiederherstellung ausstehend“ oder eine Fehlermeldung

Die Attribute zeigen `in_ha_gespeichert`, `zuletzt_gesendet` und ausdrücklich
`geraetewerte_bestaetigt: false`. Diese Informationen lassen sich auch über
die Integrationsdiagnose herunterladen. Nach einem Neustart bleiben die
lokal gespeicherten Werte erhalten; die Anzeige der letzten Übertragung
wird nur im laufenden Prozess vorgehalten.

Optional unter **Einstellungen → Geräte & Dienste → Shelly Zigbee Calibration →
Konfigurieren** die **Obergrenze für Mindestwertversuche** und den
**Gamma-Startwert für den ersten Gamma-Versuch** einstellen. Dieser Dialog
ändert nur HA-Startwerte und sendet keine Gerätebefehle. Die eigentliche
Bedienung bleibt direkt auf der vorhandenen Shelly-Geräteseite.

## Automatische Gerätekalibrierung

**Automatische Kalibrierung starten** fordert weiterhin `Light.Calibrate`
über Zigbee an. Die automatische Einmessung ist unabhängig vom manuellen
Dimmkurven-Assistenten. Die Lampe kann dabei ihre Helligkeit ändern;
während der bis zu zwei Minuten laufenden Einmessung nicht bedienen.
Nach jeder Anfrage gilt eine Sperrzeit von **130 Sekunden** im laufenden
Core-Prozess. Sie ist keine Messung des tatsächlichen Kalibrierungsfortschritts.

Das Button-Ergebnis bestätigt nur die vollständige Zigbee-Übertragung,
nicht Annahme, Start oder Abschluss der RPC-Methode. Bei Timeout könnte die
Anfrage bereits ausgeführt worden sein; die Wirkung an der Lampe prüfen und
eine möglicherweise laufende Kalibrierung nicht sofort erneut starten.
Ein ZHA-Helligkeitswert wie 2 % ist kein Kalibrierungsstatus.

## Installation über HACS

1. **HACS → ⋮ → Benutzerdefinierte Repositories** öffnen.
2. `https://github.com/MrMorice/shelly-zigbee-dimmer-calibration` eintragen,
   Kategorie **Integration** auswählen und hinzufügen.
3. **Shelly Zigbee Calibration** herunterladen und Home Assistant neu starten.
   Solange kein Release veröffentlicht wurde, wird `main` verwendet.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen →
   Shelly Zigbee Calibration** öffnen und deinen bereits in ZHA gekoppelten
   Shelly auswählen. Die Einrichtung löst keine Kalibrierung aus.

Unterstützt wird der europäische Dimmer Gen4 mit Modell `S4DM-0A101WWL` sowie
Zigbee-Modellnamen `Dimmer`, `ShellyDimmerG4` und `Shelly Dimmer Gen4`.
Der Shelly muss auf Endpunkt 239 den RPC-Cluster `0xFC01` mit Profil `0xC001`
anbieten. Die Integration öffnet keine zweite Verbindung zum Funkstick.
Das native Gamma muss von der Gerätefirmware unterstützt werden; Shelly
führt es für dieses Modell ab Firmware **2.0.0** auf. Da RPC-Ergebnisse nicht
gelesen werden, können unbekannte oder abgelehnte Parameter nicht automatisch
erkannt werden. Die Wirkung muss am physischen Gerät geprüft werden.

**Manuell:** Den gesamten Ordner `custom_components/shelly_zigbee_calibration`
aus dem ZIP nach `/config/custom_components/` kopieren und Core neu starten.
Beim Update den bisherigen Integrationsordner vollständig ersetzen, damit
entfernte Dateien nicht zurückbleiben. Der Ordner mit `configuration.yaml`
kann im Dateieditor auch als `/homeassistant` erscheinen.

Die lokalen Brand-Assets liegen unter `brand/icon.png` und `brand/icon@2x.png`.
HACS 2.0.5 kann trotz korrekter Bilder ein leeres Übersichtssymbol zeigen:
[HACS #5171](https://github.com/hacs/integration/issues/5171).

## Grenzen, Tests und Entfernen

Entwickelt für **Home Assistant Core 2026.10.2**, getestet mit echten
Core-/ZHA-/zigpy-Paketen und simuliertem Shelly. **Die tatsächliche Wirkung
des neuen Schreibmodus auf einem physischen Dimmer ist noch nicht getestet.**
Eine erfolgreiche Testsuite beweist keine Gerätekompatibilität.

Die Integration verändert keine Firmware, WLAN-Einstellungen, Kopplung oder
ZHA-Quirks. Sie führt keine RPC-Leseversuche oder automatischen RPC-Wiederholungen
aus. ZCL-Schreibbestätigungen sind für die Übertragung weiterhin erforderlich.
Native Parameter werden über partielle `Light.SetConfig`-Aufrufe gesendet;
sonstige Shelly-Einstellungen werden dabei nicht absichtlich verändert.

Vor dem Entfernen laufende Versuche und offene Abschlüsse beenden. Dann den
Integrationseintrag löschen und die Integration in HACS deinstallieren.
Der Shelly bleibt in ZHA gekoppelt; zuletzt gesendete Einstellungen können
im Gerät bleiben. Das Löschen der HA-Speicherdaten entfernt die Rücksetzwerte.

Tests in einer Python-3.14-Umgebung mit `homeassistant==2026.10.2`,
`zha==2.3.1`, `zha-quirks==2.3.0`, deren Integrationsabhängigkeiten,
`pytest` und `pytest-asyncio`:

```sh
PYTHONPATH=. python -m pytest tests -q
```

Quellen: [Shelly RPC Cluster](https://shelly-api-docs.shelly.cloud/gen2/Integrations/Zigbee/RPCCluster/),
[Light-Konfiguration](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Light/#configuration),
[Shelly-Changelog](https://shelly-api-docs.shelly.cloud/gen2/changelog/),
[Dokumentiertes RPC-Leseproblem](https://github.com/Koenkk/zigbee-herdsman-converters/pull/12732).
