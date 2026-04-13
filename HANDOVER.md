# Handover für die nächste Session

> Briefing für den Start des neuen Repos `esphome-subaru-ssm2`.
> Dieses Dokument ist self-contained — der nächste Claude (oder du selbst)
> kann ohne Kontext aus dieser Session weiterarbeiten.

---

## Was bisher geschah

1. Altes Repo `esphome-wire-whisperer` enthielt eine zu breite Vision
   (Multi-Bus, 6 Komponenten gleichzeitig). Codex hat dazu Code generiert
   der **nicht funktioniert** (Compile-Crashes, falsches Frame-Format,
   blockierende Calls, kaputtes YAML).
2. Auf Branch `claude/fix-wire-whisperer-UbuRj` wurden alle Bugs gefixt
   (siehe Git-History).
3. Nach Reality-Check: Projekt-Scope auf **nur Subaru SSM2** reduziert.
4. Altes Repo wird archiviert, neues Repo `esphome-subaru-ssm2` wird
   aufgemacht.

---

## Was du in der neuen Session brauchst

### Aus diesem Repo mitnehmen (Branch `claude/fix-wire-whisperer-UbuRj`)
- `components/subaru_ssm2/` (komplett — Codegen, C++, Parameter)
- `examples/subaru-sg5.yaml` (als Basis für ein Minimalbeispiel umarbeiten)
- `ROADMAP.md`
- `HANDOVER.md` (dieses Doc)
- `LICENSE` (MIT)

### Was im neuen Repo NICHT mitkommt
- `components/lin_bus/` → eigenes Repo wenn Bedarf
- `components/onewire_auto/` → eigenes Repo, ist eh nur Stub
- `examples/lin-sniffer.yaml`
- Die alte breite README

### Frische Files für das neue Repo
- Neue `README.md` mit klarem Fokus (nur SSM2, klare Hardware-Liste)
- `docs/hardware.md` mit Pinout L9637D + OBD2
- `docs/protocol.md` mit SSM2-Frame-Erklärung
- `tools/gen_parameters.py` (Phase 4, später)
- `.github/workflows/ci.yaml` (Phase 8)
- Frische Git-History (`git init`, kein Codex-Müll mitschleppen)

---

## Hardware-Inventur (vom User auszufüllen)

Bitte in der nächsten Session konkret beantworten:

- [ ] **KKL-Kabel-Modell** + Foto vom Chip drinnen
      (Standard ist `L9637D` + `FT232RL`/`CH340`)
- [ ] **ESP-Modell** (ESP32-C3-DevKitM-1? Anderer?)
- [ ] **OBD2-Pinbelegung am Subaru** mit Multimeter verifiziert?
      - Pin 7 idle ~12 V?
      - Pin 4/5 GND?
      - Pin 16 +12 V?
- [ ] **Lötkolben + Multimeter** verfügbar?
- [ ] **Fahrzeug-Modell + Modelljahr** (für ECU-ID-Lookup in RomRaider)

---

## Erste Aufgaben für die nächste Session

In dieser Reihenfolge:

### 1. Repo-Setup
- Neues Repo `esphome-subaru-ssm2` anlegen (GitHub).
- Files aus dieser Session rüberkopieren (siehe oben).
- `git init` lokal, frische History, erster Commit "Initial scaffold".
- README + ROADMAP + HANDOVER pushen.

### 2. RomRaider-Parameter ziehen
- Klonen: `git clone https://github.com/RomRaider/RomRaider`
- Datei: `RomRaider/src/main/resources/com/romraider/logger/ecu/def/logger.xml`
  (oder via deren Release-Definitions-Repo)
- ECU-ID des User-Subaru rausfinden (steht im RomRaider definitions repo
  unter dem Modelljahr).
- Erstmal **manuell** die 5–10 wichtigsten Parameter (Coolant, RPM, MAF,
  Boost, IAM, Battery, IAT, TPS) extrahieren und unsere
  `ssm2_parameters.h` damit ersetzen.

### 3. Frame-Format final verifizieren
Aktueller Code in `subaru_ssm2.cpp` sendet:
```
0x80 0x10 0xF0 0x05 0xA8 0x00 0x00 0x00 [param] [csum]
```
Das ist eine Single-Address-Read-Anfrage mit 3-Byte-Adresse, wobei wir
nur das niedrigste Byte variabel machen. **Verifizieren** anhand FreeSSM
Source-Code (`src/SSMprotocol2.cpp`), ob:
- Pad-Byte (0x00) zwischen `0xA8` und der Adresse korrekt ist
- Adresse wirklich Big-Endian 3 Bytes ist
- Checksum die simple 8-bit-Summe ist (NICHT `~sum`)

Die Checksum-Variante ist der wahrscheinlichste Bug. Mein aktueller Code
nutzt `sum & 0xFF` (richtig laut FreeSSM), Codex hatte ursprünglich
`~(sum & 0xFF)` (falsch).

### 4. Loopback-Test (Phase 1 der Roadmap)
- ESP TX↔RX brücken
- `esphome run` mit DEBUG-Logger
- Hex-Output vergleichen mit erwartetem Frame
- Wenn das stimmt → erst dann Hardware ans Auto.

### 5. Sniff-Modus bauen
Mini-Erweiterung der Komponente: YAML-Option `mode: sniff` →
sendet nichts, loggt nur RX-Bytes als Hex. Für den ersten Test am Auto
ohne Risiko.

---

## Bekannte offene Punkte / Risiken

- **Adressformat unsicher**: aktueller Code nutzt nur das low byte als
  Parameter-Adresse. Echte SSM2-Adressen sind 3 Bytes (z.B. RAM
  `0x000008` für Coolant, ROM `0xFF6800`+ für Tabellen). Für Live-Daten
  unter `0xFF` zufällig ok, aber muss generalisiert werden (Phase 4).
- **Parameter-Tabelle in `ssm2_parameters.h` ist GERATEN**. Adressen,
  Scaling-Faktoren, Offsets — alles muss gegen RomRaider verifiziert
  werden bevor das Projekt veröffentlicht wird.
- **Kein Init-Handshake** im Code. SSM2 sollte ohne Init funktionieren
  (anders als KWP2000 5-Baud-Init), aber falls die ECU nicht antwortet
  ist das der erste Verdacht.
- **K-Line ist halbduplex**. Unser Code disabled aktuell nicht den
  TX-Treiber während er auf Antwort wartet. Mit L9637D macht der Chip
  das automatisch (Echo-Suppression), ohne externen Transceiver würden
  wir unsere eigenen Bytes empfangen.

---

## Quick-Reference: SSM2 Frame-Format

```
Request (Tester → ECU):
┌──────┬──────┬──────┬──────┬──────┬─────────────┬──────┐
│ 0x80 │ dest │ src  │ len  │ cmd  │ data...     │ csum │
└──────┴──────┴──────┴──────┴──────┴─────────────┴──────┘
  Hdr    ECU    Tester        A8=ReadAddr        sum&0xFF
        =0x10  =0xF0          A0=ReadBlock
                              BF=ECU-Init

Response (ECU → Tester):
┌──────┬──────┬──────┬──────┬──────┬─────────────┬──────┐
│ 0x80 │ src  │ dest │ len  │ resp │ data...     │ csum │
└──────┴──────┴──────┴──────┴──────┴─────────────┴──────┘
  Hdr    Tester ECU           cmd|0x40
        =0xF0  =0x10          (A8 → E8)

Read-Address Data-Format:
  pad(0x00) addr_hi addr_mid addr_lo
  z.B. Coolant Temp: 0x00 0x00 0x00 0x08

Mehrere Adressen pro Request möglich (Multi-Read):
  0x00 0x00 0x00 0x08  (Coolant)
  0x00 0x00 0x00 0x0E  (RPM high)
  0x00 0x00 0x00 0x0F  (RPM low)
  → ECU antwortet mit Daten in derselben Reihenfolge
```

---

## Nächster Claude: Was du tun sollst

1. Lies dieses Dokument + `ROADMAP.md`.
2. Frag den User nach den Hardware-Antworten oben.
3. Setze Phase 0 + Phase 1 der Roadmap um (Hardware-Doc, Loopback-Test).
4. **Tu nichts ohne Hardware-Verifikation**. Wenn der User noch nicht
   am Auto war: nur Loopback-Test, Sniff-Modus, Doku.
5. Halte Scope klein. Wenn dem User andere Bus-Systeme einfallen:
   freundlich aber bestimmt auf "eigenes Repo später" verweisen.
