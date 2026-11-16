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

### Graph-Visualisierung

```bash
# Mermaid (Layout optimiert)
python tools/gen_parameters.py logger.xml --graph mermaid --graph-out depends.md --graph-only

# Feste Richtung
python tools/gen_parameters.py logger.xml --graph mermaid --graph-dir TB --graph-only
python tools/gen_parameters.py logger.xml --graph mermaid --graph-dir LR --graph-out depends.md --graph-only

# Graphviz
python tools/gen_parameters.py logger.xml --graph dot --graph-out depends.dot --graph-only
dot -Tpng depends.dot -o depends.png
```

| Flag | Bedeutung |
|------|-----------|
| `--graph mermaid\|dot\|ascii` | Format |
| `--graph-out PATH` | Datei (sonst stdout) |
| `--graph-only` | Nur Graph |
| `--graph-dir LR\|RL\|TB\|BT` | Mermaid-Richtung (default: **auto**) |

**Mermaid-Layout (automatisch)**

- `%%{init}%%`: `curve: basis`, `nodeSpacing: 28`, `rankSpacing: 48`
- **auto-Richtung:** `TB` ab 12 derived-Knoten, sonst `LR`
- **Subgraphs:** `Cycles` · `Derived` · `Base`
- kurze Labels (max. ~28 Zeichen), Escaping von Sonderzeichen
- Cycle-Kanten: dicke rote `linkStyle` / `==>`

**Legende:** derived = blau · base = grau · cycle = rot

Siehe ROADMAP Phase 4.
