# SSM2 Protokoll-Kurzreferenz

## Request-Frame (Tester → ECU)

`0x80 dest src len cmd data... checksum`

- Header: `0x80`
- ECU-Destination: `0x10`
- Tester-Source: `0xF0`
- Command `0xA8`: Read Address
- Checksum: **8-bit Summe aller Bytes (`sum & 0xFF`)**

## Response-Frame (ECU → Tester)

`0x80 src dest len status data... checksum`

- Status für Read-Address Response: `0xE8`
- Bei Read-Address startet Nutzdatenbereich nach dem Statusbyte

## Single Address Read Beispiel

Request:
`80 10 F0 05 A8 00 00 00 08 CS`

- `00 00 00 08` = 3-Byte Adresse (Big-Endian) mit Pad-Byte

Erwartete Richtung der Antwort:
`80 F0 10 ... E8 ... CS`

## Diagnose-Hinweise

Wenn keine Antwort kommt:
- TX/RX tauschen prüfen
- GND-Verbindung prüfen
- Baudrate 4800 8N1 verifizieren
- mit `mode: sniff` zuerst nur passiv prüfen

Wenn Checksum nicht passt:
- prüfen, ob Summe als `sum & 0xFF` gerechnet wird
- vollständigen Frame-Hex-Log vergleichen
