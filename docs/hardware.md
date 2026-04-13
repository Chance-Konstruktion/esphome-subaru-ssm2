# Hardware-Setup (Phase 0)

## Ziel
Sicheres Bench-Setup für Subaru SSM2 über K-Line ohne Risiko für ESP oder ECU.

## Mindest-Hardware
- ESP32 (z. B. ESP32-C3-DevKitM-1)
- K-Line-Transceiver mit **L9637D**
- Subaru OBD2-Zugang
- Multimeter

## Pinout L9637D ↔ ESP ↔ OBD2
- L9637D Pin 6 (TX) → ESP RX
- L9637D Pin 1 (RX) → ESP TX
- L9637D Pin 7 (K) → OBD2 Pin 7
- L9637D Pin 4 (GND) → gemeinsame Masse
- L9637D Pin 5 (VBATT) → OBD2 Pin 16 (+12 V)
- L9637D Pin 8 (VCC) → 5 V (ESP/USB)

## OBD2-Messpunkte (vor erstem Senden prüfen)
- Pin 4/5: GND
- Pin 7: K-Line idle etwa +12 V
- Pin 16: Dauerplus +12 V

## Sicherheits-Checkliste
- [ ] Gemeinsame Masse zwischen ESP, Transceiver und Fahrzeug vorhanden
- [ ] TX/RX nicht vertauscht
- [ ] Keine offenen Leitungen mit Karosserie-Kontakt
- [ ] ESP bootet stabil bei verbundenem OBD2

## Hinweis
Erst **nach** erfolgreichem Loopback-Test aktiv an die ECU senden.
