# Loopback + Sniff (Phase 1/2)

## 1) Loopback-Test (ohne Auto)

### Verdrahtung
- ESP TX direkt auf ESP RX (3.3 V Logik)
- Kein L9637D nötig

### Ziel-Frame
`0x80 0x10 0xF0 0x05 0xA8 0x00 0x00 0x00 0x08 [csum]`

### Ablauf
1. `subaru_ssm2` normal betreiben (`mode: normal`).
2. Logger auf `VERY_VERBOSE` stellen.
3. Prüfen, ob gesendete Bytes 1:1 auf RX auftauchen.
4. Checksumme manuell gegen letztes Byte prüfen (`sum & 0xFF`).

## 2) Sniff-Modus (am Auto, listen-only)

In der YAML-Komponente:

```yaml
subaru_ssm2:
  id: subaru_ecu
  uart: kline_uart
  mode: sniff
  update_interval: 5s
  request_delay: 50ms
  response_timeout: 200ms
  parameters:
    - id: 0x08
      name: "Kühlmitteltemperatur"
```

### Verhalten
- Komponente sendet **keine** Requests.
- Eingehende Bytes werden als Hex geloggt (`Sniff RX: 0x..`).
