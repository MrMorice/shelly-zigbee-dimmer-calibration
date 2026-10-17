# Shelly Zigbee Calibration · 0.2.1

<img src="https://raw.githubusercontent.com/MrMorice/shelly-zigbee-dimmer-calibration/main/custom_components/shelly_zigbee_calibration/brand/icon%402x.png" alt="Frontaler 3D-Dimmer mit hellem Hintergrund und Kalibrierungsskala" width="128">

Kleine benutzerdefinierte Home-Assistant-Integration für **Shelly Dimmer Gen4**:
Sie ergänzt am vorhandenen ZHA-Gerät den Button **„Kalibrierung starten“**
und einen Assistenten für **native Mindesthelligkeit und Gamma**.
Die Anfrage läuft ausschließlich über Zigbee. WLAN, Shelly-Cloud, MQTT und
ZHA Toolkit werden nicht benötigt. Der vorhandene Funkstick bleibt bei ZHA.

**Stand:** Für Home Assistant **Core 2026.10.2** entwickelt. Getestet mit den
echten Core-/ZHA-/zigpy-Paketen und einem simulierten Zigbee-Gerät.
**Der neue Dimmkurven-Assistent ist noch nicht mit einem physischen Shelly getestet.**
Er benötigt funktionierende Zigbee-RPC-Leseantworten der Shelly-Firmware.
Der automatische Kalibrierungsbutton kommt weiterhin ohne diese Antworten aus.
Home Assistant OS 18.3 ist eine andere Versionsnummer; ein OS-Upgrade allein
ändert nicht die hier verwendete Core-Schnittstelle.

## Button direkt am vorhandenen Shelly

Ab Version **0.1.3** wird der Button direkt dem vorhandenen **ZHA-Shelly**
zugeordnet. Er erscheint dort im Bereich **Konfiguration**. Die Integration
registriert dafür kein zusätzliches Gerät.

Beim Update wird ein bereits vorhandener Kalibrierungsbutton automatisch auf
das ZHA-Gerät verschoben. Seine eindeutige Kennung und Entity-ID bleiben erhalten,
damit bestehende Dashboard-Verweise und Automationen weiter funktionieren.
Ein leerer Geräte-Doppeleintrag dieser Integration wird entfernt. Hat dieser
Eintrag weitere Entitäten oder untergeordnete Geräte, bleibt er erhalten.
Die vorhandene Licht-Entität und das ZHA-Gerät werden nicht verändert.

Die Integrationsverwaltung zeigt weiterhin den installierten Eintrag
**Shelly Zigbee Calibration**; der Bedienknopf gehört zum ZHA-Gerät.

## Mindesthelligkeit und Gamma direkt im Shelly

Ab **0.2.1** bedienst du den Assistenten direkt auf der **vorhandenen
Shelly-Geräteseite in ZHA → Konfiguration**. Es entstehen weder ein
zusätzliches Gerät noch eine zweite Licht-Entität. Die Einstellungen werden
über den Shelly-RPC-Cluster ausschließlich per **Zigbee** übertragen.
Die bestehende ZHA-Lichtsteuerung wird für die Helligkeitsvorschau verwendet.

1. Nach dem Update auf **0.2.1** in HACS Home Assistant neu starten. Ist kein
   Update sichtbar, über das HACS-Menü erneut herunterladen und `main` auswählen.
2. **Einstellungen → Geräte & Dienste → Geräte → deinen vorhandenen Shelly**
   öffnen und den Bereich **Konfiguration** aufklappen.
3. **Mindesthelligkeit suchen** drücken. Der Assistent liest zuerst
   `Light.GetConfig` und sichert die bisherigen Werte. Die native Untergrenze
   beginnt im Versuch bei 0 %, die Lampe wird bei 1 % angefordert.
4. **Dimmwert erhöhen (+)** erhöht die Untergrenze um 0,5 %, **Dimmwert senken (−)**
   reduziert sie entsprechend. Sobald die Lampe zuverlässig leuchtet,
   **Dimmwerte speichern** drücken. **Dimmkurven-Status** zeigt den aktuellen Wert.
5. **Gamma-Vorschau starten** drücken. Die Lampe fährt wiederholt von dunkel
   nach hell und zurück. Ein Zyklus dauert ungefähr 25 Sekunden zuzüglich
   Zigbee-Übertragungszeit. Die Knöpfe **Dimmwert erhöhen (+)** und
   **Dimmwert senken (−)** verändern jetzt Gamma jeweils um 0,1.
6. **Dimmwerte speichern** behält die Werte. **Dimmversuch abbrechen** verwirft
   die Vorschau und stellt die vorherigen Werte wieder her. Der Status zeigt
   Fehler und ausstehende Wiederherstellungen an; Details stehen in den
   Attributen des Statusfelds. Inaktive Bedienknöpfe sind ausgegraut.

Der ursprüngliche Button **Kalibrierung starten** bleibt für die automatische
Einmessung bestehen. Er ist von der manuellen Dimmkurven-Einstellung unabhängig.

Alternativ bleibt der Dialog aus 0.2.0 unter **Einstellungen → Geräte & Dienste →
Shelly Zigbee Calibration → Konfigurieren** verfügbar. Beide Oberflächen
bedienen denselben Versuch: Speichern oder Abbrechen auf einer Oberfläche
beendet ihn auch für die andere. Der Shelly ist weiterhin ein ZHA-Gerät;
die Zusatzintegration legt keinen eigenen Dimmer an.

Es werden die nativen Einstellungen `range_map` und `gamma` verändert,
keine Kurve in Home Assistant nachgebildet. Die bisherige Obergrenze bleibt
erhalten; Gamma ist auf Shellys dokumentierten Bereich 0,4–4,0 begrenzt.
`min_brightness_on_toggle` wird nicht verwendet: Dieser Wert ist keine
allgemeine Untergrenze des Dimmverlaufs.

**Während der Vorschau werden die Werte bereits im Shelly geschrieben.**
Speichern behält sie; Abbrechen oder Schließen schreibt die zuvor gelesenen
Werte zurück. Beide Wege stellen anschließend den zuvor von Home Assistant
gemeldeten Ein-/Aus-Zustand und bei eingeschalteter Lampe die vorherige
Helligkeit wieder her. Nach fünf Minuten wird automatisch abgebrochen.
Die Vorschau läuft über Home Assistant, die behaltenen Einstellungen liegen
anschließend im Shelly. Sie sollen dadurch auch für die Bedienung am Gerät
gelten; die tatsächliche Wirkung der Firmware auf Zigbee- und Tastersteuerung
muss am physischen Gerät geprüft werden.

**Firmware-Voraussetzung:** Für diesen Assistenten reicht eine bestätigte
Zigbee-Schreibübertragung nicht aus. Vor Änderungen müssen `gamma` und
`range_map` aus `Light.GetConfig` lesbar sein. Jede Änderung benötigt eine
passende RPC-Antwort und wird anschließend erneut zurückgelesen. Liefert die
Firmware keine RPC-Daten oder unterstützt sie die Parameter nicht, bricht
der erste Start ab, ohne Einstellungen oder Helligkeit zu ändern. Der
Kalibrierungsbutton bleibt trotzdem verwendbar. Die bisher beobachteten
RPC-Leseprobleme können den Assistenten also auch bei deinem Shelly verhindern.

**Bei einem unterbrochenen Versuch:** Die ursprünglichen Werte werden vor der
ersten Änderung in Home Assistant gesichert. Ist der Shelly beim Abbrechen
offline oder fällt Home Assistant aus, kann die Vorschau-Einstellung im
Shelly bleiben. Den Shelly wieder erreichbar machen und am Gerät **Dimmversuch abbrechen**
drücken: Die gesicherten Werte werden wiederhergestellt, ohne einen neuen
Versuch zu starten. Auch das Starten eines neuen Versuchs bzw. erneute Öffnen
des Optionsdialogs stellt zunächst den gesicherten Zustand wieder her. Bei einem
Core-Neustart allein werden keine Lampen oder Shelly-Einstellungen geändert.
Die Sicherung wird erst nach bestätigter Wiederherstellung bzw. erfolgreichem
Speichern gelöscht. Solange eine Wiederherstellung aussteht, bleibt der
Kalibrierungsbutton gesperrt. Die Integration bis zur Wiederherstellung nicht
entfernen und die zugehörigen `.storage`-Daten nicht löschen.

Während eines Versuchs keine anderen RPC-Clients, Automationen oder Taster
verwenden, die dieselbe Lampe oder deren Konfiguration verändern. Die
Integration verhindert Überschneidungen ihres Assistenten und ihres
Kalibrierungsbuttons; externe Zugriffe kann sie nicht sperren.

## Integrationsbild

Der frontal ausgerichtete 3D-Dimmer mit hellem Studiountergrund wird als lokales Home-Assistant-Brand-Asset in
`brand/icon.png` (256 × 256) und `brand/icon@2x.png` (512 × 512) mit deckendem Hintergrund
ausgeliefert. Im Home-Assistant-Integrationsdialog wird es nach Update und
Neustart verwendet. Diese README zeigt es auch in der HACS-Detailbeschreibung.

**HACS 2.0.5:** Die Übersicht kann trotz korrekter lokaler Bilder ein leeres
Symbol zeigen. Das ist eine bekannte HACS-Einschränkung und kein Fehler des
Bildpfads. Siehe [HACS #5171](https://github.com/hacs/integration/issues/5171).

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
      options_flow.py
      curve.py
      runtime.py
      wizard.py
      device_controls.py
      sensor.py
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

Zuerst laufende Versuche abbrechen und eine ausstehende Wiederherstellung
abschließen. Unter **Einstellungen → Geräte & Dienste** den Eintrag
**Shelly Zigbee Calibration** löschen. Gespeicherte native Dimmwerte bleiben im Shelly. Anschließend kann der zugehörige Ordner aus `custom_components`
entfernt und Home Assistant neu gestartet werden. Das ZHA-Gerät bleibt gekoppelt.

## Technische Grundlage

- Shelly RPC über Zigbee: Profil vom vorhandenen Geräteendpunkt, Endpunkt 239,
  Cluster `0xFC01`, Herstellerkennung `0x1490`.
- Zuerst RPC-Bytelänge in `TxCtl`, dann JSON in 40-Byte-Stücken in `Data`.
- Kalibrierungsbutton: `Light.Calibrate`, Parameter `{"id": 0}`.
- Assistent: `Light.GetConfig` und partielle `Light.SetConfig`-Aufrufe für
  `gamma` und `range_map`, mit bestätigter RPC-Antwort und Rücklesen.
  Nur die Vorschau-Helligkeit läuft über die vorhandene ZHA-Licht-Entität.
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
- [Shelly RPC Cluster](https://shelly-api-docs.shelly.cloud/gen2/Integrations/Zigbee/RPCCluster/)
- [Zigbee2MQTT-Shelly-Implementierung](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/shelly.ts)
- [Native Light-Konfiguration](https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Light/#configuration)
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
