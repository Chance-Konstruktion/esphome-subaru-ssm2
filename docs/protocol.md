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

- `len = 0x05` = `cmd(1) + responseType(1) + 3-Byte-Adresse(3)`
- `A8` = Read Addresses, `00` = responseType (single)
- `00 00 08` = 3-Byte Adresse (Big-Endian)

Erwartete Richtung der Antwort:
`80 F0 10 len E8 data… CS`

- `len` zählt `status(1) + data(N)` (ohne Checksum)

## Mehrbyte-Werte (z. B. RPM)

`0xA8` liefert **ein Byte pro angefragter Adresse**. Ein 2-Byte-Wert braucht
also zwei Adressen in einem Request — die ECU antwortet in derselben
Reihenfolge:

Request RPM (`0x0E` = High, `0x0F` = Low):
`80 10 F0 08 A8 00  00 00 0E  00 00 0F  CS`

Antwort:
`80 F0 10 03 E8 <byte_0E> <byte_0F> CS`

Konvention im Code: die Tabellen-Adresse ist das niederwertigste Byte;
angefragt wird `(addr-N+1 … addr)` aufsteigend (= MSB zuerst).

## Echo auf der K-Line

K-Line ist Single-Wire-Halbduplex: das gesendete Request-Frame kommt 1:1 auf
RX zurück. Der Parser sucht den ECU-Header `80 F0 10` und überspringt das Echo
(`80 10 F0 …`) damit automatisch.

## Diagnose-Hinweise

Wenn keine Antwort kommt:
- TX/RX tauschen prüfen
- GND-Verbindung prüfen
- Baudrate 4800 8N1 verifizieren
- mit `mode: sniff` zuerst nur passiv prüfen

Wenn Checksum nicht passt:
- prüfen, ob Summe als `sum & 0xFF` gerechnet wird
- vollständigen Frame-Hex-Log vergleichen
