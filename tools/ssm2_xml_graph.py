#!/usr/bin/env python3
"""
Depends-Graph aus RomRaider logger.xml extrahieren und visualisieren.

Formate:
  - mermaid  → GitHub/Markdown-fähig
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


def _safe_id(pid: str) -> str:
    """Mermaid/DOT-sichere Node-ID."""
    s = _ID_SAFE.sub("_", pid)
    if s and s[0].isdigit():
        s = "n_" + s
    return s or "node"


@dataclass
class DependsGraph:
    """derived_id → set of dependency parameter ids (+ metadata)."""

    edges: dict[str, set[str]] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)  # id → display name
    base_nodes: set[str] = field(default_factory=set)  # non-derived targets
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

    # Collect names for all parameters
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

    # base_nodes should not include derived
    g.base_nodes -= g.derived_nodes
    return g


def _label(g: DependsGraph, pid: str) -> str:
    name = g.names.get(pid, "")
    if name and name != pid:
        return f"{pid}\n{name}"
    return pid


def render_ascii(g: DependsGraph, cycles: list[list[str]] | None = None) -> str:
    lines: list[str] = []
    lines.append(f"Depends-Graph: {len(g.derived_nodes)} derived, "
                 f"{len(g.base_nodes)} base, {len(g.edge_list())} edges")
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


def render_mermaid(g: DependsGraph, cycles: list[list[str]] | None = None) -> str:
    cycle_nodes: set[str] = set()
    cycle_edges: set[tuple[str, str]] = set()
    if cycles:
        for cyc in cycles:
            body = cyc[:-1] if len(cyc) > 1 and cyc[0] == cyc[-1] else cyc
            for n in body:
                cycle_nodes.add(n)
            for i in range(len(body)):
                a, b = body[i], body[(i + 1) % len(body)]
                cycle_edges.add((a, b))

    lines = ["```mermaid", "flowchart LR"]
    # Nodes
    for pid in sorted(g.derived_nodes):
        sid = _safe_id(pid)
        lab = _label(g, pid).replace('"', "'")
        if pid in cycle_nodes:
            lines.append(f'  {sid}["{lab}"]:::cycle')
        else:
            lines.append(f'  {sid}["{lab}"]:::derived')
    for pid in sorted(g.base_nodes):
        sid = _safe_id(pid)
        lab = _label(g, pid).replace('"', "'")
        lines.append(f'  {sid}[("{lab}")]:::base')

    # Edges
    for src, dst in g.edge_list():
        ss, ds = _safe_id(src), _safe_id(dst)
        if (src, dst) in cycle_edges:
            lines.append(f"  {ss} -->|cycle| {ds}")
        else:
            lines.append(f"  {ss} --> {ds}")

    lines += [
        "  classDef derived fill:#dbeafe,stroke:#2563eb,color:#1e3a8a;",
        "  classDef base fill:#f3f4f6,stroke:#6b7280,color:#374151;",
        "  classDef cycle fill:#fee2e2,stroke:#dc2626,color:#7f1d1d;",
        "```",
        "",
    ]
    return "\n".join(lines)


def render_dot(g: DependsGraph, cycles: list[list[str]] | None = None) -> str:
    cycle_nodes: set[str] = set()
    cycle_edges: set[tuple[str, str]] = set()
    if cycles:
        for cyc in cycles:
            body = cyc[:-1] if len(cyc) > 1 and cyc[0] == cyc[-1] else cyc
            for n in body:
                cycle_nodes.add(n)
            for i in range(len(body)):
                a, b = body[i], body[(i + 1) % len(body)]
                cycle_edges.add((a, b))

    lines = [
        "digraph depends {",
        "  rankdir=LR;",
        "  node [fontname=\"Helvetica\"];",
        "  // derived = box, base = ellipse, cycle = red",
    ]
    for pid in sorted(g.derived_nodes):
        sid = _safe_id(pid)
        lab = _label(g, pid).replace('"', "\\\"")
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
        lab = _label(g, pid).replace('"', "\\\"")
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
) -> str:
    """Build graph, detect cycles, render. Optionally write to ``out``."""
    g = build_depends_graph(xml_path)
    # Cycle detection only on derived→derived edges (same as validator)
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
        text = render_mermaid(g, cycles)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    return text
