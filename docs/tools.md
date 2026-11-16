# Tools

## `tools/gen_parameters.py` — RomRaider → `ssm2_parameters.h`

Generiert die C++-Parameter-Tabelle aus einer RomRaider `logger.xml`.
Enthält eine praxisnahe **Schema-/Struktur-Validierung** (ohne harte Abhängigkeit von einer einzelnen `logger.dtd`-Version).

### Voraussetzungen

- Python 3.10+
- Eine RomRaider Logger-Definition (`logger.xml`)

### Schnellstart

```bash
# Nur validieren
python tools/gen_parameters.py path/to/logger.xml --validate-only
python tools/gen_parameters.py path/to/logger.xml --validate-only --strict

# ECU-IDs in der Definition anzeigen
python tools/gen_parameters.py path/to/logger.xml --list-ecus

# Für eine konkrete ECU generieren (Validierung läuft vorher automatisch)
python tools/gen_parameters.py path/to/logger.xml \
  --ecu 2F12785606 \
  -o components/subaru_ssm2/ssm2_parameters.h

# Generierung trotz Validierungsfehlern erzwingen
python tools/gen_parameters.py path/to/logger.xml --ecu 2F12785606 --skip-validate
```

### Wichtige Flags

| Flag | Bedeutung |
|------|-----------|
| `--validate-only` | Nur prüfen, keinen Header schreiben |
| `--strict` | Mehr Warnings bei ungewöhnlichen Attributen |
| `--skip-validate` | Validierung vor dem Generieren überspringen |
| `--ecu ID` | Nur Parameter dieser ECU-ID (mehrfach möglich) |
| `--list-ecus` | Alle ECU-IDs aus der XML auflisten |
| `--no-ecuparam` | ECU-spezifische `<ecuparam>`-Blöcke ignorieren |
| `--all` | Auch weniger gebräuchliche Parameter mitnehmen |
| `-o PATH` | Ausgabedatei (Default: `components/subaru_ssm2/ssm2_parameters.h`) |

### Was die Validierung prüft

**Struktur**
- Root / `protocol` bzw. `logprotocol` vorhanden
- `<parameter>` und `<ecuparam>` mit `id`/`name`
- Entweder `<address>` oder `<depends>`
- `<depends>/<ref>` mit `parameter` oder `ecuparam`
- `<ecuparam>` idealerweise mit `<ecu id="...">`-Unterblöcken

**Adressen**
- Hex-Format (`0x...` oder plain hex)
- 24-bit-Bereich (`0 … 0xFFFFFF`)
- `length` / `bit`-Attribute im plausiblen Rahmen
- ECU-ID-Format (soft)

**Conversions**
- `expr` Pflicht
- Übersetzbarkeit in `scale`/`offset` (einfache Formen)
- Hinweis bei komplexen/derived Ausdrücken
- optionale `storagetype` / `format`-Plausibilität

**Konsistenz**
- doppelte Parameter-IDs
- Statistik (counts, convertible vs. complex)

Exit-Code: `0` = keine Errors, `1` = mindestens ein Error.

### Hinweise zum Generator

- Globale `<parameter>` werden immer berücksichtigt.
- `<ecuparam>` nur, wenn `--ecu` matched (oder kein Filter gesetzt ist).
- Derived-Parameter (`<depends>`) werden beim Codegen übersprungen.
- Nur einfache Ausdrücke (`x-40`, `x/4`, `x*0.001`, …) werden in `scale`/`offset` übersetzt.
- Adressen werden vorerst als Low-Byte geschrieben (kompatibel zum aktuellen C++-Code). Die volle 24-bit-Adresse steht als Kommentar im generierten Header.

Siehe auch ROADMAP Phase 4.
