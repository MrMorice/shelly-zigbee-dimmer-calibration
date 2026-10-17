# Shelly Zigbee Calibration · 0.1.2

Kleine benutzerdefinierte Home-Assistant-Integration für **Shelly Dimmer Gen4**:
Sie ergänzt am vorhandenen ZHA-Gerät den Button **„Kalibrierung starten“**.
Die Anfrage läuft ausschließlich über Zigbee. WLAN, Shelly-Cloud, MQTT und
ZHA Toolkit werden nicht benötigt. Der vorhandene Funkstick bleibt bei ZHA.

**Stand:** Für Home Assistant **Core 2026.10.2** entwickelt. Getestet mit den
echten Core-/ZHA-/zigpy-Paketen und einem simulierten Zigbee-Gerät.
**Noch nicht mit einem physischen Shelly getestet.** Die erste Kalibrierung
ist deshalb ein Praxistest, keine zugesicherte Gerätekompatibilität.
Home Assistant OS 18.3 ist eine andere Versionsnummer; ein OS-Upgrade allein
ändert nicht die hier verwendete Core-Schnittstelle.

## Über HACS installieren

1. In HACS oben rechts **⋮ → Benutzerdefinierte Repositories** öffnen.
2. Repository `https://github.com/MrMorice/shelly-zigbee-dimmer-calibration`
   eintragen, Kategorie **Integration** auswählen und hinzufügen.
3. **Shelly Zigbee Calibration** in HACS suchen und herunterladen.
   Solange kein Release veröffentlicht wurde, wird der Standardzweig `main` verwendet.
4. Home Assistant neu starten.
5. **Einstellungen → Geräte & Dienste → Integration hinzufügen →
   Shelly Zigbee Calibration** öffnen und deinen Dimmer auswählen.

Die Einrichtung startet keine Kalibrierung. Für jedes weitere Gerät kann ein
weiterer Integrationseintrag angelegt werden. Bereits manuell installierte
Dateien desselben Integrationsordners können von HACS verwaltet werden;
bei der Installation ersetzt HACS diesen Ordner durch die Repository-Version.

## Manuell installieren


1. ZIP auf deinem Computer entpacken.
2. Den gesamten Ordner `custom_components/shelly_zigbee_calibration` nach
   `/config/custom_components/shelly_zigbee_calibration` auf dem Green kopieren.
   Der Ordner `/config` wird im Dateieditor je nach Oberfläche auch als
   `/homeassistant` angezeigt. Gemeint ist der Ordner mit `configuration.yaml`.
   Falls `custom_components` fehlt, diesen Ordner anlegen.
   Das geht beispielsweise über die Samba-Freigabe oder Studio Code Server.
3. Home Assistant **neu starten** (Core-Neustart reicht).
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen** öffnen und
   **Shelly Zigbee Calibration** suchen.
5. Deinen bereits in ZHA gekoppelten Shelly auswählen. Das Einrichten löst
   noch keine Kalibrierung aus.

Die Dateien müssen so liegen, ohne einen zusätzlichen ZIP-Ordner dazwischen:

```text
/config/
  configuration.yaml
  custom_components/
    shelly_zigbee_calibration/
      __init__.py
      manifest.json
      button.py
      config_flow.py
      const.py
      helpers.py
      rpc.py
      strings.json
      translations/
        de.json
```

## Benutzen

Am ausgewählten Shelly-Gerät erscheint unter **Konfiguration** der Button
**Kalibrierung starten**. Du kannst ihn auch einem Dashboard hinzufügen.
Der Button startet die automatische Einmessung der angeschlossenen Lampe;
deren Helligkeit kann sich dabei ändern. Während der bis zu zwei Minuten
laufenden Kalibrierung die Lampe nicht bedienen.

Das Attribut **ergebnis** am Button unterscheidet:

- **„Befehl vollständig übertragen; Start und Abschluss an der Lampe prüfen“**:
  Alle Zigbee-Schreibzugriffe wurden vom Gerät bestätigt. Dies bestätigt weder
  die Annahme der RPC-Methode noch einen erfolgreichen Kalibrierungsabschluss.
  Laut Shelly leuchtet die Lampe nach erfolgreicher Kalibrierung zehn Sekunden
  und schaltet dann aus. Danach das tatsächliche Dimmen prüfen.
- **Fehler oder fehlende Bestätigung**: Die Fehlermeldung steht am Button und
  im Home-Assistant-Protokoll. Bei einer fehlenden Antwort kann die
  Kalibrierung trotzdem schon laufen. Zwei Minuten abwarten und die Lampe prüfen.

Nach jeder Anfrage gibt es eine Sperrzeit von **130 Sekunden**, um doppelte
Starts zu vermeiden. Die Sperrzeit besteht nur im laufenden Core-Prozess;
ein Neustart oder Neuladen hebt sie auf. Das ist kein Anlass, eine noch
laufende Kalibrierung erneut zu starten.

## Falls etwas fehlt oder nicht funktioniert

- Integration wird nicht gefunden: Ordnerstruktur prüfen, Core neu starten,
  Browserseite neu laden und das Protokoll prüfen.
- Kein Dimmer gefunden: Unterstützt wird der europäische Dimmer Gen4 mit
  Modell `S4DM-0A101WWL` sowie den Zigbee-Modellnamen `Dimmer`, `ShellyDimmerG4` und
  `Shelly Dimmer Gen4`. Er muss bei ZHA gekoppelt sein und auf Endpunkt 239
  den RPC-Cluster `0xFC01` mit Profil `0xC001` anbieten. Andere Dimmer und
  Shelly-Relais werden absichtlich nicht ausgewählt.
- Nicht neu koppeln und keinen Werksreset durchführen, nur weil die Integration
  das Gerät nicht erkennt. Für eine Anpassung sind die **ZHA-Gerätediagnose**,
  die Shelly-Firmwareversion und die Fehlermeldung hilfreich. Diagnose vor dem
  Teilen auf persönliche Daten prüfen.
- Timeout: Die Meldung nennt jetzt den Schritt (`TxCtl schreiben`, `Data schreiben`
  oder im optionalen Diagnosepfad `RxCtl/Data lesen`). Bei einer möglicherweise
  vollständig übertragenen Anfrage mindestens zwei Minuten abwarten. Es gibt
  keine automatischen Wiederholungen.
- Ein Helligkeitswert von 2 % in ZHA ist kein Kalibrierungsstatus. Nach Ablauf
  der Kalibrierung die reale Lampe mit unterschiedlichen Helligkeiten testen.
- Gleichzeitige Zugriffe anderer Programme auf Shellys RPC-Mailbox vermeiden.
  Die Integration serialisiert nur ihre eigenen Anfragen. Normales Schalten
  über den ZHA-Lichtausgang benutzt einen anderen Cluster.

Die Integration verändert keine Firmware, WLAN-Konfiguration, Kopplung oder
ZHA-Quirks. Sie repariert nicht automatisch eine andere Ursache für fehlendes
Dimmen. Zukünftige Core-/ZHA-Versionen können Anpassungen notwendig machen,
da Home Assistant für Zusatzintegrationen keine stabile öffentliche API zum
ZHA-Controller garantiert.

## Entfernen

Unter **Einstellungen → Geräte & Dienste** den Eintrag **Shelly Zigbee Calibration**
löschen. Anschließend kann der zugehörige Ordner aus `custom_components`
entfernt und Home Assistant neu gestartet werden. Das ZHA-Gerät bleibt gekoppelt.

## Technische Grundlage

- Shelly RPC über Zigbee: Profil vom vorhandenen Geräteendpunkt, Endpunkt 239,
  Cluster `0xFC01`, Herstellerkennung `0x1490`.
- Zuerst RPC-Bytelänge in `TxCtl`, dann JSON in 40-Byte-Stücken in `Data`.
- Methode ausschließlich `Light.Calibrate`, Parameter `{"id": 0}`.
- Die normale Button-Aktion prüft die ZCL-Schreibantworten und liest die
  RPC-Mailbox nicht aus. Die Zigbee2MQTT-Referenzimplementierung dokumentiert
  fehlende RPC-Data-Leseantworten bei Shelly-Firmware, auch 2.0.0. Deshalb
  wird kein Kalibrierungserfolg aus einer fehlenden Antwort abgeleitet.
- Ein optionaler interner Diagnosepfad (`calibrate(confirm=True)`) kann die
  RPC-Antwort begrenzt auslesen und anhand von RPC-ID und Zielkennung zuordnen.
  Er ist nicht Teil der normalen Button-Aktion.
- Globale ZCL-Antworten mit und ohne Herstellerkopf werden nach Zuordnung
  über Gerät, Profil, Cluster, Endpunkte und Sequenznummer akzeptiert.
  Default Responses werden nur beim passenden ursprünglichen Befehl verarbeitet.
  Eine Leseantwort ohne Daten wird nicht als erfolgreiche RPC-Antwort behandelt.
- Der Registry-Aufruf ist auf den ZHA-Konfigurationseintrag begrenzt und nutzt
  die aktuelle API von Core 2026.10.2.
- Temporärer zigpy-Nachrichtenlistener statt Änderungen am Core. Dadurch können
  auch Antworten auf Shellys eigenem Profil verarbeitet werden.
- Keine automatischen Wiederholungen auf Anwendungsebene.

Quellen:

- [Shelly Dimmer Gen4](https://shelly-api-docs.shelly.cloud/gen2/Devices/Gen4/ShellyDimmerG4/)
- [Shelly RPC Cluster](https://shelly-api-docs.shelly.cloud/gen2/Integrations/Zigbee/CustomClusters/RPCCluster/)
- [Zigbee2MQTT-Shelly-Implementierung](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/shelly.ts)
- [Light.Calibrate](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Light/#lightcalibrate)
- [Kalibrierung und Anzeigen am Gerät](https://kb.shelly.cloud/knowledge-base/shelly-dimmer-gen4)

## Tests ausführen

In einer separaten Python-3.14-Umgebung mit `homeassistant==2026.10.2`,
`zha==2.3.1`, `zha-quirks==2.3.0`, deren deklarierten Integrationsabhängigkeiten,
`pytest` und `pytest-asyncio`:

```sh
PYTHONPATH=. python -m pytest tests -q
```

Die Tests verwenden echte Home-Assistant-Klassen und zigpy-ZCL-Serializer.
Das entfernte Shelly-Gerät wird simuliert. Es wird kein Funkstick geöffnet.
