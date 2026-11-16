# Tools

## `tools/gen_parameters.py` — RomRaider → `ssm2_parameters.h`

Generiert die C++-Parameter-Tabelle aus einer RomRaider `logger.xml`.
Enthält Schema-Validierung, Ref-Existenz, Zyklenerkennung und **Graph-Export**.

### Module

| Datei | Rolle |
|-------|--------|
| `tools/gen_parameters.py` | CLI |
| `tools/ssm2_xml_common.py` | Shared helpers |
| `tools/ssm2_xml_validate.py` | Schema-/Ref-Validierung + Cycle-Finder |
| `tools/ssm2_xml_generate.py` | Parse + Header-Generator |
| `tools/ssm2_xml_graph.py` | Depends-Graph → Mermaid / DOT / ASCII |

### Schnellstart

```bash
python tools/gen_parameters.py path/to/logger.xml --validate-only
python tools/gen_parameters.py path/to/logger.xml --list-ecus
python tools/gen_parameters.py path/to/logger.xml --ecu 2F12785606 -o components/subaru_ssm2/ssm2_parameters.h
```

### Graph-Visualisierung

```bash
# Mermaid (GitHub-README / Markdown-Preview)
python tools/gen_parameters.py logger.xml --graph mermaid --graph-out depends.md --graph-only

# Graphviz DOT → PNG
python tools/gen_parameters.py logger.xml --graph dot --graph-out depends.dot --graph-only
dot -Tpng depends.dot -o depends.png

# Kompakte Textliste
python tools/gen_parameters.py logger.xml --graph ascii --graph-only
```

| Flag | Bedeutung |
|------|-----------|
| `--graph mermaid\|dot\|ascii` | Format wählen |
| `--graph-out PATH` | In Datei schreiben (sonst stdout) |
| `--graph-only` | Nur Graph, kein Header |

**Legende**

- **derived** (blau/Box): Parameter mit `<depends>`
- **base** (grau/Ellipse): referenzierte Basis-Parameter
- **cycle** (rot): Knoten/Kanten in einem erkannten Zyklus

### Ref-Existenz (`depends`)

- Pass 1 sammelt alle `parameter`-/`ecuparam`-IDs (und Name→ID)
- `<ref parameter="…">` muss existieren (sonst **error**)
- Selbst-Referenz → **error**
- Zyklen im Derived-Graphen → **error** (iterative DFS, dedupliziert)
- Statistik: `unresolved_refs`, `self_refs`, `dep_cycles`

Exit-Code: `0` ohne Errors, `1` bei Errors.

Siehe ROADMAP Phase 4.
