# esphome-subaru-ssm2

ESPHome External Component für Subaru **SSM2 über K-Line (4800 8N1)**.

## Quickstart (5 Minuten)

1. Hardware laut `docs/hardware.md` verkabeln.
2. `components/subaru_ssm2/` als External Component einbinden.
3. UART auf 4800 8N1 konfigurieren.
4. Erst **Loopback-Test** (ohne Auto), dann Sniff-Mode am Auto.
5. Danach `mode: normal` aktivieren und erste Parameter lesen.

Siehe Details in:
- `docs/hardware.md`
- `docs/loopback_and_sniff.md`
- `docs/protocol.md`

## Minimalbeispiel

```yaml
external_components:
  - source: github://Chance-Konstruktion/esphome-subaru-ssm2@main
    components: [subaru_ssm2]

uart:
  - id: kline_uart
    tx_pin: GPIO6
    rx_pin: GPIO5
    baud_rate: 4800
    data_bits: 8
    stop_bits: 1
    parity: NONE

subaru_ssm2:
  id: subaru_ecu
  uart: kline_uart
  mode: normal   # sniff = listen-only
  update_interval: 5s
  request_delay: 50ms
  response_timeout: 200ms
  parameters:
    - id: 0x08
      name: "Kühlmitteltemperatur"
      unit_of_measurement: "°C"
```

## Modus

- `mode: normal` → aktive Requests an ECU
- `mode: sniff` → passiv, keine Requests; RX-Daten werden als Hex geloggt

## Projektstatus

Roadmap und Handover:
- `ROADMAP.md`
- `HANDOVER.md`
