# Roadmap: `esphome-subaru-ssm2`

> ESPHome External Component für passives & aktives Auslesen von Subaru-ECUs
> über das SSM2-Protokoll (K-Line, 4800 Baud).

Diese Roadmap ist **bewusst klein gehalten**. Das Projekt wird *erst dann*
erweitert, wenn die jeweils vorherige Phase **an echter Hardware** verifiziert
ist. Keine Vaporware, kein Multi-Bus-Wunschdenken.

---

## Phase 0 — Hardware & Bench-Setup

**Ziel:** Sicheres physisches Setup, ohne dass etwas durchbrennt.

### Tasks
- [ ] Vorhandenes VAG-KKL-Kabel öffnen, **L9637D** identifizieren (oder
      separates L9637D-Modul beschaffen, ~2 €).
- [ ] Pegelwandler-Pinout dokumentieren:
      - L9637D Pin 6 (TX) → ESP RX
      - L9637D Pin 1 (RX) → ESP TX
      - L9637D Pin 7 (K) → OBD2 Pin 7
      - L9637D Pin 4 (GND) → gemeinsame Masse
      - L9637D Pin 5 (VBATT) → 12 V vom Auto
      - L9637D Pin 8 (VCC) → 5 V vom ESP/USB
- [ ] Multimeter-Check am OBD2-Stecker des Subaru:
      - Pin 4/5: GND
      - Pin 7: K-Line, idle ~12 V (Pull-up zur Batterie)
      - Pin 16: +12 V Dauer
- [ ] Foto/Skizze der finalen Verdrahtung in `docs/hardware.md`.

### Erfolgskriterium
- ESP fährt sauber hoch wenn am OBD2 angeschlossen.
- Keine Rauchzeichen.

---

## Phase 1 — Loopback-Test (ohne Auto)

**Ziel:** Verifizieren, dass unser Frame-Format + Checksum stimmen, *bevor*
wir die ECU anfassen.

### Tasks
- [ ] ESP TX direkt auf ESP RX brücken (3.3 V, kein L9637D nötig).
- [ ] Komponente `subaru_ssm2` mit `level: VERY_VERBOSE` Logger laufen lassen.
- [ ] Prüfen ob die gesendeten Bytes 1:1 wieder im RX-Buffer ankommen:
      `0x80 0x10 0xF0 0x05 0xA8 0x00 0x00 0x00 0x08 [csum]`
- [ ] Checksum manuell nachrechnen und mit dem letzten Byte vergleichen.

### Erfolgskriterium
- Logger zeigt exakt das, was wir gesendet haben.
- Checksum stimmt.

### Deliverable
- Eventuelle Bugfixes im Frame-Bau.

---

## Phase 2 — Passiver Sniff am Auto (Listen-Only)

**Ziel:** Wir wollen sehen *was die ECU überhaupt sagt*, bevor wir selbst
senden. Schützt uns vor Frame-Format-Annahmen die falsch sind.

### Tasks
- [ ] Neue Mini-Komponente `ssm2_sniffer` (oder Flag in `subaru_ssm2`):
      sendet **nichts**, loggt jedes empfangene Byte als Hex.
- [ ] Auto auf Zündung Stellung 2 (ECU an, Motor aus).
- [ ] 30 s Log mitschneiden.
- [ ] Falls **nichts** reinkommt: das ist normal — Subaru-ECU sendet nur auf
      Anfrage. Dann direkt zu Phase 3.
- [ ] Falls Bytes reinkommen (anderes Tool aktiv?): Frame-Struktur prüfen.

### Erfolgskriterium
- Wir wissen ob die K-Line-Verkabelung physisch funktioniert (Idle-Pegel,
  keine Framing-Errors).

---

## Phase 3 — Erste Antwort von der ECU

**Ziel:** *Ein einziger* erfolgreicher Request → Response Roundtrip.

### Tasks
- [ ] **Init-Sequenz** klären: SSM2 braucht (anders als KWP2000) keine
      5-Baud-Init. Direkt Frame senden.
- [ ] Single-Address-Read für Coolant Temp (`0x000008`):
      `0x80 0x10 0xF0 0x05 0xA8 0x00 0x00 0x00 0x08 [csum]`
- [ ] Erwartete Antwort:
      `0x80 0xF0 0x10 0x03 0xE8 [data] [csum]`
- [ ] Hex-Log beider Richtungen vergleichen.
- [ ] Wert dekodieren: Coolant Temp = `raw - 40` °C.

### Erfolgskriterium
- ECU antwortet.
- Dekodierter Wert ist plausibel (-40 … +120 °C, bei warmer ECU > 60 °C).

### Mögliche Probleme
- Kein Response → Kabel-Polung tauschen, GND prüfen, Baud-Rate prüfen.
- Falsche Bytes → Frame-Format aus FreeSSM-Source nochmal querchecken.
- Checksum-Mismatch → unsere `checksum_()` ist `~sum` vs `sum & 0xFF` —
  beides mal probieren.

---

## Phase 4 — RomRaider-XML-Import

**Ziel:** Echte Parameter-Definitionen statt geratener Werte.

### Tasks
- [ ] `RomRaider/RomRaider` GitHub klonen, `logger.xml` extrahieren.
- [ ] Python-Skript `tools/gen_parameters.py` schreiben:
      - parst `logger.xml`
      - filtert nach ECU-ID des SG5 (z.B. `2F12785606`)
      - generiert `components/subaru_ssm2/ssm2_parameters_<ecu_id>.h`
- [ ] Adressformat im C++-Code auf **echte 3-Byte-Adressen** umstellen
      (`0xFF 0x68 0x00`-Bereiche etc., nicht nur die low byte).
- [ ] In YAML auswählbar machen welche ECU-Definition geladen wird.

### Erfolgskriterium
- Mindestens 5 Parameter (Coolant, RPM, Boost, IAM, Battery) liefern
  plausible Werte am laufenden Motor.

---

## Phase 5 — Block-Read (Performance)

**Ziel:** Mehrere Parameter in *einem* Request lesen statt N einzelne.
Drastisch schneller, weniger Bus-Last.

### Tasks
- [ ] SSM2 Command `0xA0` (Read Block) implementieren:
      Liest N aufeinanderfolgende Bytes ab einer Startadresse.
- [ ] Alternativ: Multi-Address-Read in einem `0xA8`-Frame
      (Address-Block kann mehrere 3-Byte-Adressen enthalten).
- [ ] Heuristik: Parameter nach Adresse sortieren, kontiguierende Blöcke
      finden, in einem Request abfragen.
- [ ] Polling-Rate testen: Ziel 5–10 Hz für Live-Daten.

### Erfolgskriterium
- 15+ Parameter @ 5 Hz ohne Timeout, ohne Watchdog-Reset.

---

## Phase 6 — Diagnostic Trouble Codes (DTCs)

**Ziel:** Fehlercodes auslesen und in Home Assistant exposen.

### Tasks
- [ ] SSM2 Command für DTC-Read recherchieren (FreeSSM Source).
- [ ] DTC-Tabelle einbauen (P-Codes mit Klartext, deutsch + englisch).
- [ ] `text_sensor` mit aktuell gesetzten DTCs.
- [ ] Optional: Service zum DTC-Reset (`text` button in HA).

### Erfolgskriterium
- Bekannter Fehler (z.B. ausgesteckter Sensor) wird korrekt angezeigt.

---

## Phase 7 — Mehrere ECU-Generationen

**Ziel:** Nicht nur SG5 EJ20 — auch andere Subaru-Plattformen.

### Tasks
- [ ] ECU-ID-Erkennung beim Boot (SSM2 hat einen ECU-ID-Request).
- [ ] Auto-Selection der passenden Parameter-Definition.
- [ ] Test-Berichte sammeln: SH EJ25, SJ FA20, GR/GV STI, BR Outback.
- [ ] Issues-Template "Add ECU support" mit Anleitung was zu loggen ist.

### Erfolgskriterium
- Mindestens 2 verschiedene ECU-Generationen verifiziert.

---

## Phase 8 — Release & Community

**Ziel:** Sauberer 1.0-Release.

### Tasks
- [ ] CI-Pipeline (GitHub Actions): `esphome config examples/*.yaml`
      gegen aktuelles ESPHome.
- [ ] Pre-built Beispiele für gängige ESP32-Boards.
- [ ] Eintrag in:
      - [ESPHome External Components Wiki](https://github.com/esphome/awesome-esphome)
      - r/Subaru, r/homeassistant
      - RomRaider/FreeSSM Foren
- [ ] Tag `v1.0.0` mit GitHub Release.

### Erfolgskriterium
- Jemand der nicht ich ist hat es erfolgreich an seinem Subaru in Betrieb.

---

## Bewusst NICHT auf der Roadmap

Diese Punkte wurden gestrichen weil sie das Projekt verwässern oder
außerhalb von ESPHome-Limits liegen:

- ❌ LIN-Bus-Sniffer → eigenes Repo wenn Bedarf
- ❌ CAN/TWAI-Support → SSM3 ist CAN-basiert, das ist ein eigenes Protokoll
- ❌ 1-Wire Auto-Discovery → ESPHome-Architektur erlaubt keine
       Runtime-Sensor-Erstellung
- ❌ "Anomalie-Erkennung", ML, Cloud-Features → gehört nach Home Assistant
- ❌ Multi-Bus-Vereinheitlichung → ein Repo pro Bus = wartbar

---

## Tech-Stack (final)

- **Sprache:** C++ (Component) + Python (Codegen) — ESPHome External Component
- **Hardware-Min:** ESP32 (jede Variante), L9637D K-Line-Transceiver
- **Protokoll:** Subaru SSM2 über K-Line ISO 9141 (4800 8N1)
- **Quellen:**
  - [FreeSSM](https://github.com/Comer352L/FreeSSM) — Referenz-Implementierung in C++
  - [RomRaider](https://github.com/RomRaider/RomRaider) — Parameter-Definitionen (`logger.xml`)
  - [BTSSM](https://github.com/inomatic/btssm) — Bluetooth-SSM-Bridge, gute Frame-Beispiele
