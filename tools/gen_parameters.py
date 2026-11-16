#!/usr/bin/env python3
"""
RomRaider logger.xml → ssm2_parameters.h Generator
für esphome-subaru-ssm2

Usage:
  # Nur globale Parameter
  python tools/gen_parameters.py logger.xml

  # Mit ECU-ID-Filter (empfohlen)
  python tools/gen_parameters.py logger.xml --ecu 2F12785606
  python tools/gen_parameters.py logger.xml --ecu 3152584006 --ecu 2F12785606

  # Alle parsebaren Parameter + ECU-spezifisch
  python tools/gen_parameters.py logger.xml --ecu 2F12785606 --all \
      -o components/subaru_ssm2/ssm2_parameters.h

  # ECU-IDs in einer Definition auflisten
  python tools/gen_parameters.py logger.xml --list-ecus
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Expression → scale/offset
# ---------------------------------------------------------------------------

EXPR_PATTERNS = [
    (re.compile(r"^\s*\(?\s*x\s*([+-])\s*([0-9.]+)\s*\)?\s*$", re.I), "offset"),
    (re.compile(r"^\s*x\s*/\s*([0-9.]+)\s*$", re.I), "div"),
    (re.compile(r"^\s*x\s*\*\s*([0-9.]+)\s*$", re.I), "mul"),
    (re.compile(r"^\s*\(?\s*x\s*([+-])\s*([0-9.]+)\s*\)?\s*/\s*([0-9.]+)\s*$", re.I), "offset_div"),
    (re.compile(r"^\s*x\s*\*\s*([0-9.]+)\s*/\s*([0-9.]+)\s*$", re.I), "mul_div"),
    (re.compile(r"^\s*x\s*$", re.I), "identity"),
]

PREFERRED_UNITS = {
    "c": 10,
    "°c": 10,
    "bar": 9,
    "rpm": 8,
    "%": 7,
    "v": 6,
    "g/s": 5,
    "°": 4,
    "deg": 4,
    "kpa": 3,
    "psi": 2,
}

USEFUL_NAMES = [
    "coolant",
    "engine speed",
    "rpm",
    "manifold",
    "boost",
    "intake air",
    "iat",
    "throttle",
    "tps",
    "accelerator",
    "battery",
    "mass air",
    "maf",
    "ignition",
    "timing",
    "knock",
    "iam",
    "wastegate",
    "fuel",
    "a/f",
    "afr",
    "oil temp",
    "vehicle speed",
    "load",
]


@dataclass
class ParsedParam:
    name: str
    address: int  # low byte (kompatibel zum aktuellen C++-Code)
    full_address: int  # komplette 24-bit Adresse (für spätere Erweiterung)
    data_length: int
    scale: float
    offset: float
    unit: str
    is_signed: bool
    expr: str
    original_id: str
    source: str  # "parameter" | "ecuparam"
    ecu_ids: list[str] = field(default_factory=list)


def parse_expr(expr: str) -> Optional[tuple[float, float]]:
    """Wandelt einfache RomRaider-Ausdrücke in (scale, offset) um."""
    expr = expr.strip()
    for pat, kind in EXPR_PATTERNS:
        m = pat.match(expr)
        if not m:
            continue
        if kind == "identity":
            return 1.0, 0.0
        if kind == "offset":
            sign, val = m.group(1), float(m.group(2))
            # x-40 → scale=1, offset=-40
            # x+40 → scale=1, offset=+40
            return 1.0, -val if sign == "-" else val
        if kind == "div":
            return 1.0 / float(m.group(1)), 0.0
        if kind == "mul":
            return float(m.group(1)), 0.0
        if kind == "offset_div":
            sign, val, div = m.group(1), float(m.group(2)), float(m.group(3))
            scale = 1.0 / div
            off = (-val if sign == "-" else val) / div
            return scale, off
        if kind == "mul_div":
            return float(m.group(1)) / float(m.group(2)), 0.0
    return None


def unit_score(units: str) -> int:
    u = units.lower().replace("°", "").strip()
    return PREFERRED_UNITS.get(u, 0)


def is_useful(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in USEFUL_NAMES)


def normalize_ecu_id(ecu_id: str) -> str:
    """ECU-IDs vergleichbar machen (Groß/Klein, führende Nullen entfernen)."""
    return ecu_id.strip().upper().lstrip("0") or "0"


def extract_byte_addresses(container: ET.Element) -> list[int]:
    """Alle <byte>…</byte> oder direkten Text-Inhalte aus einem address-Block holen."""
    addrs: list[int] = []
    text = (container.text or "").strip()
    if text:
        try:
            addrs.append(int(text, 0))
        except ValueError:
            pass
    for byte_el in container.findall("byte"):
        t = (byte_el.text or "").strip()
        if t:
            try:
                addrs.append(int(t, 0))
            except ValueError:
                pass
    return addrs


def get_addresses_for_ecu(
    param_el: ET.Element, wanted_ecu_ids: set[str] | None
) -> tuple[list[int], list[str]]:
    """
    Liefert (sorted unique addresses, matched_ecu_ids).

    - Bei normalen <parameter>: alle Adressen, ecu_ids = []
    - Bei <ecuparam>: nur Adressen der passenden <ecu id="..."> Blöcke
    """
    matched_ecus: list[str] = []
    addrs: list[int] = []

    for addr_el in param_el.findall("address"):
        # Variante 1: direkte Adresse (alte Parameter)
        direct = extract_byte_addresses(addr_el)
        if direct and not list(addr_el.findall("ecu")):
            addrs.extend(direct)
            continue

        # Variante 2: <ecu id="..."> Unterblöcke (ecuparam)
        for ecu_el in addr_el.findall("ecu"):
            ecu_id = ecu_el.get("id") or ""
            if not ecu_id:
                continue
            norm = normalize_ecu_id(ecu_id)
            if wanted_ecu_ids is None or norm in wanted_ecu_ids or ecu_id in wanted_ecu_ids:
                matched_ecus.append(ecu_id)
                addrs.extend(extract_byte_addresses(ecu_el))

    # Fallback: manche Definitionen haben die Adresse direkt unter parameter
    if not addrs:
        for byte_el in param_el.findall("byte"):
            t = (byte_el.text or "").strip()
            if t:
                try:
                    addrs.append(int(t, 0))
                except ValueError:
                    pass

    return sorted(set(addrs)), matched_ecus


def pick_conversion(param_el: ET.Element) -> Optional[tuple[str, str]]:
    """Pick best conversion (prefer metric). Returns (units, expr)."""
    candidates = []
    for conv in param_el.findall(".//conversion"):
        units = conv.get("units") or conv.get("metric") or ""
        expr = conv.get("expr") or ""
        if expr:
            candidates.append((unit_score(units), units, expr))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, units, expr = candidates[0]
    return units, expr


def parse_logger_xml(
    path: Path,
    ecu_ids: list[str] | None = None,
    include_ecuparams: bool = True,
) -> list[ParsedParam]:
    tree = ET.parse(path)
    root = tree.getroot()

    wanted: set[str] | None = None
    if ecu_ids:
        wanted = {normalize_ecu_id(e) for e in ecu_ids}
        # auch die Rohform behalten, falls die XML führende Nullen hat
        wanted |= set(ecu_ids)

    results: list[ParsedParam] = []

    # 1) Globale Parameter
    for param in root.findall(".//parameter"):
        if param.find("depends") is not None:
            continue
        name = param.get("name") or param.get("id") or "unknown"
        pid = param.get("id") or name

        addrs, _ = get_addresses_for_ecu(param, None)
        if not addrs:
            continue

        conv = pick_conversion(param)
        if not conv:
            continue
        units, expr = conv
        parsed = parse_expr(expr)
        if parsed is None:
            continue
        scale, offset = parsed

        data_length = len(addrs)
        full_addr = addrs[-1]
        low_byte = full_addr & 0xFF

        is_signed = any(
            k in name.lower() for k in ("knock", "timing", "correction", "retard")
        )

        results.append(
            ParsedParam(
                name=name,
                address=low_byte,
                full_address=full_addr,
                data_length=data_length,
                scale=scale,
                offset=offset,
                unit=units,
                is_signed=is_signed,
                expr=expr,
                original_id=pid,
                source="parameter",
                ecu_ids=[],
            )
        )

    # 2) ECU-spezifische Parameter (ecuparam)
    if include_ecuparams:
        for ecuparam in root.findall(".//ecuparam"):
            name = ecuparam.get("name") or ecuparam.get("id") or "unknown"
            pid = ecuparam.get("id") or name

            addrs, matched = get_addresses_for_ecu(ecuparam, wanted)
            if not addrs:
                continue
            # Wenn ein ECU-Filter gesetzt ist und nichts gematcht hat → überspringen
            if wanted is not None and not matched:
                continue

            conv = pick_conversion(ecuparam)
            if not conv:
                continue
            units, expr = conv
            parsed = parse_expr(expr)
            if parsed is None:
                continue
            scale, offset = parsed

            data_length = len(addrs)
            full_addr = addrs[-1]
            low_byte = full_addr & 0xFF
            is_signed = any(
                k in name.lower() for k in ("knock", "timing", "correction", "retard")
            )

            results.append(
                ParsedParam(
                    name=name,
                    address=low_byte,
                    full_address=full_addr,
                    data_length=data_length,
                    scale=scale,
                    offset=offset,
                    unit=units,
                    is_signed=is_signed,
                    expr=expr,
                    original_id=pid,
                    source="ecuparam",
                    ecu_ids=matched,
                )
            )

    # Duplikate nach low-byte-Adresse auflösen (nützliche Namen / ecuparam bevorzugen)
    by_addr: dict[int, ParsedParam] = {}
    for p in results:
        if p.address not in by_addr:
            by_addr[p.address] = p
            continue
        existing = by_addr[p.address]
        if p.source == "ecuparam" and existing.source == "parameter" and wanted:
            by_addr[p.address] = p
        elif is_useful(p.name) and not is_useful(existing.name):
            by_addr[p.address] = p

    return sorted(by_addr.values(), key=lambda x: x.address)


def generate_header(
    params: list[ParsedParam], source: str, ecu_ids: list[str] | None
) -> str:
    ecu_comment = (
        f"ECU filter: {', '.join(ecu_ids)}"
        if ecu_ids
        else "ECU filter: none (global parameters only)"
    )
    lines = [
        "#pragma once",
        "",
        "#include <cstdint>",
        "#include <map>",
        "",
        "namespace esphome {",
        "namespace subaru_ssm2 {",
        "",
        "// Auto-generated from RomRaider logger definition",
        f"// Source : {source}",
        f"// {ecu_comment}",
        "// DO NOT EDIT BY HAND – regenerate with tools/gen_parameters.py",
        "",
        "struct SSM2Parameter {",
        "  uint8_t address;",
        "  const char *name;",
        "  const char *unit;",
        "  float scale;",
        "  float offset;",
        "  uint8_t data_length;",
        "  bool is_signed;",
        "};",
        "",
        "static const std::map<uint8_t, SSM2Parameter> KNOWN_PARAMETERS = {",
    ]

    for p in params:
        unit_c = f'"{p.unit}"' if p.unit else "nullptr"
        name_c = p.name.replace('"', '\\"')
        comment = ""
        if p.ecu_ids:
            comment = f"  // ECU: {', '.join(p.ecu_ids)}  full=0x{p.full_address:06X}"
        elif p.full_address > 0xFF:
            comment = f"  // full=0x{p.full_address:06X}"
        lines.append(
            f'    {{0x{p.address:02X}, {{0x{p.address:02X}, "{name_c}", {unit_c}, '
            f"{p.scale:.6g}f, {p.offset:.6g}f, {p.data_length}, "
            f"{'true' if p.is_signed else 'false'}}}}},{comment}"
        )

    lines += [
        "};",
        "",
        "}  // namespace subaru_ssm2",
        "}  // namespace esphome",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="RomRaider logger.xml → ssm2_parameters.h (mit optionalem ECU-ID-Filter)"
    )
    ap.add_argument("xml", type=Path, help="Pfad zur logger.xml")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("components/subaru_ssm2/ssm2_parameters.h"),
    )
    ap.add_argument(
        "--ecu",
        action="append",
        dest="ecu_ids",
        metavar="ECU_ID",
        help="ECU-ID filtern (mehrfach möglich). Beispiel: --ecu 2F12785606",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Alle parsebaren Parameter ausgeben (nicht nur 'nützliche')",
    )
    ap.add_argument(
        "--no-ecuparam",
        action="store_true",
        help="ECU-spezifische <ecuparam>-Blöcke ignorieren",
    )
    ap.add_argument(
        "--list-ecus",
        action="store_true",
        help="Nur alle gefundenen ECU-IDs aus der XML auflisten und beenden",
    )
    args = ap.parse_args()

    if not args.xml.exists():
        print(f"Datei nicht gefunden: {args.xml}", file=sys.stderr)
        return 1

    if args.list_ecus:
        tree = ET.parse(args.xml)
        ecu_ids = set()
        for ecu in tree.getroot().findall(".//ecu"):
            eid = ecu.get("id")
            if eid:
                ecu_ids.add(eid)
        if not ecu_ids:
            print('Keine <ecu id="..."> Einträge gefunden.')
        else:
            print(f"Gefundene ECU-IDs ({len(ecu_ids)}):")
            for eid in sorted(ecu_ids):
                print(f"  {eid}")
        return 0

    params = parse_logger_xml(
        args.xml,
        ecu_ids=args.ecu_ids,
        include_ecuparams=not args.no_ecuparam,
    )

    if not args.all:
        params = [p for p in params if is_useful(p.name)]

    if not params:
        print("Keine verwertbaren Parameter gefunden.", file=sys.stderr)
        if args.ecu_ids:
            print(
                "Tipp: --list-ecus ausführen, um verfügbare ECU-IDs zu sehen.",
                file=sys.stderr,
            )
        return 1

    header = generate_header(params, str(args.xml), args.ecu_ids)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(header, encoding="utf-8")

    print(f"Wrote {len(params)} parameters → {args.output}")
    if args.ecu_ids:
        print(f"ECU filter : {', '.join(args.ecu_ids)}")
    print()
    for p in params:
        src = f"[{p.source}]"
        ecu = f" ECU={','.join(p.ecu_ids)}" if p.ecu_ids else ""
        print(
            f"  0x{p.address:02X}  {p.name:32s}  len={p.data_length}  "
            f"scale={p.scale:g}  offset={p.offset:g}  [{p.unit}]  {src}{ecu}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
