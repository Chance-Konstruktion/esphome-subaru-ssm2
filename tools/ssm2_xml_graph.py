#!/usr/bin/env python3
"""
Depends-Graph aus RomRaider logger.xml extrahieren und visualisieren.

Formate:
  - mermaid  → GitHub/Markdown-fähig (Layout optimiert)
  - dot      → Graphviz (dot -Tpng graph.dot -o graph.png)
  - ascii    → kompakte Text-Zusammenfassung
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from ssm2_xml_validate import find_dependency_cycles

_ID_SAFE = re.compile(r"[^0-9A-Za-z_]")
_MERMAID_ESC = re.compile(r"[\"\[\]{}|]")


def _safe_id(pid: str) -> str:
    """Mermaid/DOT-sichere Node-ID."""
    s = _ID_SAFE.sub("_", pid)
    if s and s[0].isdigit():
        s = "n_" + s
    return s or "node"


def _mermaid_label(text: str, max_len: int = 28) -> str:
    """Label kürzen und für Mermaid-Node-Text entschärfen."""
    t = " ".join(text.split())  # Newlines/Whitespace kollabieren
    t = _MERMAID_ESC.sub("", t)
    t = t.replace("<", "&lt;").replace(">", "&gt;")
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t


@dataclass
class DependsGraph:
    """derived_id → set of dependency parameter ids (+ metadata)."""

    edges: dict[str, set[str]] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    base_nodes: set[str] = field(default_factory=set)
    derived_nodes: set[str] = field(default_factory=set)

    def edge_list(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for src, deps in sorted(self.edges.items()):
            for dst in sorted(deps):
                out.append((src, dst))
        return out


def build_depends_graph(path: Path) -> DependsGraph:
    tree = ET.parse(path)
    root = tree.getroot()
    g = DependsGraph()

    for param in root.findall(".//parameter"):
        pid = (param.get("id") or "").strip()
        pname = (param.get("name") or pid or "?").strip()
        if pid:
            g.names[pid] = pname

    for param in root.findall(".//parameter"):
        pid = (param.get("id") or "").strip()
        if not pid:
            continue
        depends = param.find("depends")
        if depends is None:
            continue
        g.derived_nodes.add(pid)
        deps: set[str] = set()
        for ref in depends.findall("ref"):
            ref_param = (ref.get("parameter") or "").strip()
            if ref_param and ref_param != pid:
                deps.add(ref_param)
        g.edges[pid] = deps
        for d in deps:
            if d not in g.derived_nodes:
                g.base_nodes.add(d)

    g.base_nodes -= g.derived_nodes
    return g


def _label(g: DependsGraph, pid: str) -> str:
    name = g.names.get(pid, "")
    if name and name != pid:
        return f"{pid} {name}"
    return pid


def _cycle_sets(
    cycles: list[list[str]] | None,
) -> tuple[set[str], set[tuple[str, str]]]:
    cycle_nodes: set[str] = set()
    cycle_edges: set[tuple[str, str]] = set()
    if not cycles:
        return cycle_nodes, cycle_edges
    for cyc in cycles:
        body = cyc[:-1] if len(cyc) > 1 and cyc[0] == cyc[-1] else cyc
        for n in body:
            cycle_nodes.add(n)
        for i in range(len(body)):
            a, b = body[i], body[(i + 1) % len(body)]
            cycle_edges.add((a, b))
    return cycle_nodes, cycle_edges


def _pick_direction(g: DependsGraph, direction: str | None) -> str:
    """
    Richtung wählen.
    - explizit: LR/RL/TB/BT
    - auto: TB wenn viele derived (tiefere Hierarchie lesbarer),
            sonst LR (klassischer Abhängigkeitsfluss)
    """
    if direction:
        d = direction.upper()
        if d in {"LR", "RL", "TB", "BT"}:
            return d
    n = len(g.derived_nodes)
    # Heuristik: ab ~12 derived-Knoten stapeln statt horizontal spreizen
    return "TB" if n >= 12 else "LR"


def render_ascii(g: DependsGraph, cycles: list[list[str]] | None = None) -> str:
    lines: list[str] = []
    lines.append(
        f"Depends-Graph: {len(g.derived_nodes)} derived, "
        f"{len(g.base_nodes)} base, {len(g.edge_list())} edges"
    )
    if cycles:
        lines.append(f"Zyklen: {len(cycles)}")
        for cyc in cycles:
            lines.append("  CYCLE " + " → ".join(cyc))
    lines.append("")
    for src, deps in sorted(g.edges.items()):
        label = g.names.get(src, src)
        if not deps:
            lines.append(f"{src}  ({label})  →  (keine refs)")
            continue
        dep_s = ", ".join(sorted(deps))
        lines.append(f"{src}  ({label})  →  {dep_s}")
    return "\n".join(lines) + "\n"


def render_mermaid(
    g: DependsGraph,
    cycles: list[list[str]] | None = None,
    direction: str | None = None,
) -> str:
    """
    Layout-Optimierungen:
    - init-Directive: basis-Kurven, Abstände
    - Richtung LR/TB (auto-Heuristik)
    - Subgraphs: Cycles / Derived / Base (stärkt hierarchisches Layout)
    - kurze Labels, Escaping
    - linkStyle für Cycle-Kanten (rot, dick)
    """
    cycle_nodes, cycle_edges = _cycle_sets(cycles)
    rankdir = _pick_direction(g, direction)

    lines: list[str] = [
        "```mermaid",
        "%%{init: {",
        '  "flowchart": {',
        '    "htmlLabels": false,',
        '    "curve": "basis",',
        '    "nodeSpacing": 28,',
        '    "rankSpacing": 48,',
        '    "padding": 12',
        "  },",
        '  "themeVariables": { "fontSize": "12px" }',
        "} }%%",
        f"flowchart {rankdir}",
    ]

    # --- Subgraph: cycles first (visuell oben/links) ---
    if cycle_nodes:
        lines.append('  subgraph CYC["⚠ Cycles"]')
        lines.append("    direction LR")
        for pid in sorted(cycle_nodes):
            if pid not in g.derived_nodes and pid not in g.base_nodes:
                continue
            sid = _safe_id(pid)
            lab = _mermaid_label(_label(g, pid))
            lines.append(f'    {sid}["{lab}"]:::cycle')
        lines.append("  end")

    # --- Derived (ohne reine Cycle-only-Wiederholung: trotzdem listen,
    #     Mermaid merged gleiche IDs; Klasse cycle hat Vorrang wenn schon gesetzt)
    derived_plain = sorted(g.derived_nodes - cycle_nodes)
    if derived_plain:
        lines.append('  subgraph DER["Derived"]')
        lines.append(f"    direction {rankdir}")
        for pid in derived_plain:
            sid = _safe_id(pid)
            lab = _mermaid_label(_label(g, pid))
            lines.append(f'    {sid}["{lab}"]:::derived')
        lines.append("  end")

    # --- Base sinks ---
    base_plain = sorted(g.base_nodes - cycle_nodes)
    if base_plain:
        lines.append('  subgraph BASE["Base"]')
        lines.append("    direction LR")
        for pid in base_plain:
            sid = _safe_id(pid)
            lab = _mermaid_label(_label(g, pid))
            lines.append(f'    {sid}[("{lab}")]:::base')
        lines.append("  end")

    # Falls ein Cycle-Node nur als base vorkommt
    for pid in sorted(cycle_nodes & g.base_nodes):
        sid = _safe_id(pid)
        lab = _mermaid_label(_label(g, pid))
        lines.append(f'  {sid}[("{lab}")]:::cycle')

    # --- Edges (stabil sortiert); Cycle-Kanten merken für linkStyle ---
    edge_lines: list[str] = []
    cycle_edge_indices: list[int] = []
    edge_idx = 0
    for src, dst in g.edge_list():
        ss, ds = _safe_id(src), _safe_id(dst)
        if (src, dst) in cycle_edges:
            edge_lines.append(f"  {ss} ==> {ds}")
            cycle_edge_indices.append(edge_idx)
        else:
            edge_lines.append(f"  {ss} --> {ds}")
        edge_idx += 1
    lines.extend(edge_lines)

    # linkStyle nur auf Cycle-Kanten (nachträglich, indexbasiert)
    for i in cycle_edge_indices:
        lines.append(f"  linkStyle {i} stroke:#dc2626,stroke-width:2.5px")

    lines += [
        "  classDef derived fill:#dbeafe,stroke:#2563eb,color:#1e3a8a,rx:4,ry:4;",
        "  classDef base fill:#f3f4f6,stroke:#6b7280,color:#374151;",
        "  classDef cycle fill:#fee2e2,stroke:#dc2626,color:#7f1d1d,stroke-width:2px;",
        "```",
        "",
    ]
    return "\n".join(lines)


def render_dot(g: DependsGraph, cycles: list[list[str]] | None = None) -> str:
    cycle_nodes, cycle_edges = _cycle_sets(cycles)

    lines = [
        "digraph depends {",
        "  rankdir=LR;",
        '  node [fontname="Helvetica"];',
        "  // derived = box, base = ellipse, cycle = red",
    ]
    for pid in sorted(g.derived_nodes):
        sid = _safe_id(pid)
        lab = _label(g, pid).replace('"', '\\"')
        if pid in cycle_nodes:
            lines.append(
                f'  {sid} [label="{lab}", shape=box, style="filled,bold", '
                f'fillcolor="#fee2e2", color="#dc2626"];'
            )
        else:
            lines.append(
                f'  {sid} [label="{lab}", shape=box, style=filled, '
                f'fillcolor="#dbeafe", color="#2563eb"];'
            )
    for pid in sorted(g.base_nodes):
        sid = _safe_id(pid)
        lab = _label(g, pid).replace('"', '\\"')
        lines.append(
            f'  {sid} [label="{lab}", shape=ellipse, style=filled, '
            f'fillcolor="#f3f4f6", color="#6b7280"];'
        )

    for src, dst in g.edge_list():
        ss, ds = _safe_id(src), _safe_id(dst)
        if (src, dst) in cycle_edges:
            lines.append(f'  {ss} -> {ds} [color="#dc2626", penwidth=2];')
        else:
            lines.append(f"  {ss} -> {ds};")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def export_graph(
    xml_path: Path,
    fmt: str = "mermaid",
    out: Path | None = None,
    direction: str | None = None,
) -> str:
    """Build graph, detect cycles, render. Optionally write to ``out``."""
    g = build_depends_graph(xml_path)
    derived_only = {
        src: {d for d in deps if d in g.derived_nodes}
        for src, deps in g.edges.items()
    }
    cycles = find_dependency_cycles(derived_only)

    fmt = fmt.lower().strip()
    if fmt == "dot":
        text = render_dot(g, cycles)
    elif fmt == "ascii":
        text = render_ascii(g, cycles)
    else:
        text = render_mermaid(g, cycles, direction=direction)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return text
