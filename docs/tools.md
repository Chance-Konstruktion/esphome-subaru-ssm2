# Tools

## `tools/gen_parameters.py` — RomRaider → `ssm2_parameters.h`

Generiert die C++-Parameter-Tabelle aus einer RomRaider `logger.xml`.

### Voraussetzungen

- Python 3.10+
- Eine RomRaider Logger-Definition (`logger.xml`)

### Schnellstart

```bash
# ECU-IDs in der Definition anzeigen
python tools/gen_parameters.py path/to/logger.xml --list-ecus

# Für eine konkrete ECU generieren (empfohlen)
python tools/gen_parameters.py path/to/logger.xml \
  --ecu 2F12785606 \
  -o components/subaru_ssm2/ssm2_parameters.h

# Alle parsebaren Parameter (nicht nur die „nützlichen“)
python tools/gen_parameters.py path/to/logger.xml --ecu 2F12785606 --all
```

### Wichtige Flags

| Flag | Bedeutung |
|------|-----------|
| `--ecu ID` | Nur Parameter dieser ECU-ID (mehrfach möglich) |
| `--list-ecus` | Alle ECU-IDs aus der XML auflisten |
| `--no-ecuparam` | ECU-spezifische `<ecuparam>`-Blöcke ignorieren |
| `--all` | Auch weniger gebräuchliche Parameter mitnehmen |
| `-o PATH` | Ausgabedatei (Default: `components/subaru_ssm2/ssm2_parameters.h`) |

### Hinweise

- Globale `<parameter>` werden immer berücksichtigt.
- `<ecuparam>` nur, wenn `--ecu` matched (oder kein Filter gesetzt ist).
- Derived-Parameter (`<depends>`) werden übersprungen.
- Nur einfache Ausdrücke (`x-40`, `x/4`, `x*0.001`, …) werden in `scale`/`offset` übersetzt.
- Adressen werden vorerst als Low-Byte geschrieben (kompatibel zum aktuellen C++-Code). Die volle 24-bit-Adresse steht als Kommentar im generierten Header.

Siehe auch ROADMAP Phase 4.
