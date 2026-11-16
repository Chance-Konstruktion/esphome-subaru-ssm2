# Tools

## `tools/gen_parameters.py` — RomRaider → `ssm2_parameters.h`

Generiert die C++-Parameter-Tabelle aus einer RomRaider `logger.xml`.
Enthält eine praxisnahe **Schema-/Struktur-Validierung** inkl. **Ref-Existenz** und **depends-Zyklen**.

### Module

| Datei | Rolle |
|-------|--------|
| `tools/gen_parameters.py` | CLI |
| `tools/ssm2_xml_common.py` | Shared helpers |
| `tools/ssm2_xml_validate.py` | Schema-/Ref-Validierung |
| `tools/ssm2_xml_generate.py` | Parse + Header-Generator |

### Schnellstart

```bash
python tools/gen_parameters.py path/to/logger.xml --validate-only
python tools/gen_parameters.py path/to/logger.xml --validate-only --strict
python tools/gen_parameters.py path/to/logger.xml --list-ecus
python tools/gen_parameters.py path/to/logger.xml --ecu 2F12785606 -o components/subaru_ssm2/ssm2_parameters.h
```

### Ref-Existenz (`depends`)

- Pass 1 sammelt alle `parameter`-/`ecuparam`-IDs (und Name→ID)
- `<ref parameter="…">` muss existieren (sonst **error**)
- `<ref ecuparam="…">` analog
- Soft-Auflösung über Display-`name` (**info**)
- Selbst-Referenz → **error**
- Zyklen im Derived-Graphen → **error**
- Statistik: `unresolved_refs`, `self_refs`, `dep_cycles`

Exit-Code: `0` ohne Errors, `1` bei Errors.

Siehe ROADMAP Phase 4.
