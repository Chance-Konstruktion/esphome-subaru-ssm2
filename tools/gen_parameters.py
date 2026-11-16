#!/usr/bin/env python3
"""
RomRaider logger.xml → ssm2_parameters.h Generator
für esphome-subaru-ssm2

Usage:
  # Nur globale Parameter
  python tools/gen_parameters.py logger.xml

  # Mit ECU-ID-Filter (empfohlen)
  python tools/gen_parameters.py logger.xml --ecu 2F12785606

  # Schema-/Struktur-Validierung ohne Header-Ausgabe
  python tools/gen_parameters.py logger.xml --validate-only
  python tools/gen_parameters.py logger.xml --validate-only --strict

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

# Erweiterte Erkennung „komplex, aber syntaktisch ok“ (nur Validate, kein Codegen)
COMPLEX_EXPR_HINT = re.compile(
    r"[a-zA-Z_][a-zA-Z0-9_]*|P\d+|\[|\]|GetLogParam|if\s*\(|\?", re.I
)

HEX_ADDR_RE = re.compile(r"^(0x)?[0-9a-fA-F]+$")
ECU_ID_RE = re.compile(r"^[0-9A-Za-z._-]{4,32}$")

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

KNOWN_ROOT_TAGS = {"logger", "logprotocols", "protocols"}
KNOWN_PROTOCOL_IDS = {"SSM", "SSM2", "OBD", "ISO9141"}  # soft hint only


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


@dataclass
class ValidationIssue:
    level: str  # "error" | "warning" | "info"
    path: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level.upper():7s}] {self.path}: {self.message}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
            return 1.0, -val if sign == "-" else val
        if kind == "div":
            denom = float(m.group(1))
            if denom == 0:
                return None
            return 1.0 / denom, 0.0
        if kind == "mul":
            return float(m.group(1)), 0.0
        if kind == "offset_div":
            sign, val, div = m.group(1), float(m.group(2)), float(m.group(3))
            if div == 0:
                return None
            scale = 1.0 / div
            off = (-val if sign == "-" else val) / div
            return scale, off
        if kind == "mul_div":
            num, den = float(m.group(1)), float(m.group(2))
            if den == 0:
                return None
            return num / den, 0.0
    return None


def unit_score(units: str) -> int:
    u = units.lower().replace("°", "").strip()
    return PREFERRED_UNITS.get(u, 0)


def is_useful(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in USEFUL_NAMES)


def normalize_ecu_id(ecu_id: str) -> str:
    return ecu_id.strip().upper().lstrip("0") or "0"


def element_path(el: ET.Element, root: ET.Element) -> str:
    """Best-effort XPath-ähnlicher Pfad für Meldungen."""
    tag = el.tag
    pid = el.get("id") or el.get("name")
    if pid:
        return f"{tag}[@id='{pid}']" if el.get("id") else f"{tag}[@name='{pid}']"
    return tag


def parse_address_token(text: str) -> Optional[int]:
    text = (text or "").strip()
    if not text:
        return None
    if not HEX_ADDR_RE.match(text):
        return None
    try:
        return int(text, 0 if text.lower().startswith("0x") else 16)
    except ValueError:
        try:
            return int(text, 16)
        except ValueError:
            return None


def extract_byte_addresses(container: ET.Element) -> list[int]:
    addrs: list[int] = []
    text = (container.text or "").strip()
    if text:
        val = parse_address_token(text)
        if val is not None:
            addrs.append(val)
    for byte_el in container.findall("byte"):
        t = (byte_el.text or "").strip()
        if t:
            val = parse_address_token(t)
            if val is not None:
                addrs.append(val)
    return addrs


def get_addresses_for_ecu(
    param_el: ET.Element, wanted_ecu_ids: set[str] | None
) -> tuple[list[int], list[str]]:
    matched_ecus: list[str] = []
    addrs: list[int] = []

    for addr_el in param_el.findall("address"):
        direct = extract_byte_addresses(addr_el)
        if direct and not list(addr_el.findall("ecu")):
            addrs.extend(direct)
            continue

        for ecu_el in addr_el.findall("ecu"):
            ecu_id = ecu_el.get("id") or ""
            if not ecu_id:
                continue
            norm = normalize_ecu_id(ecu_id)
            if wanted_ecu_ids is None or norm in wanted_ecu_ids or ecu_id in wanted_ecu_ids:
                matched_ecus.append(ecu_id)
                addrs.extend(extract_byte_addresses(ecu_el))

    if not addrs:
        for byte_el in param_el.findall("byte"):
            t = (byte_el.text or "").strip()
            if t:
                val = parse_address_token(t)
                if val is not None:
                    addrs.append(val)

    return sorted(set(addrs)), matched_ecus


def pick_conversion(param_el: ET.Element) -> Optional[tuple[str, str]]:
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


# ---------------------------------------------------------------------------
# Schema / structural validation
# ---------------------------------------------------------------------------

def validate_logger_xml(path: Path, strict: bool = False) -> list[ValidationIssue]:
    """
    Strukturelle + semantische Prüfung einer RomRaider logger.xml.

    Kein vollständiger DTD-Parser (logger.dtd variiert über Versionen), sondern
    praxisnahe Regeln aus bekannten logger.xml / logger.dtd Varianten.
    """
    issues: list[ValidationIssue] = []

    def err(path_s: str, msg: str) -> None:
        issues.append(ValidationIssue("error", path_s, msg))

    def warn(path_s: str, msg: str) -> None:
        issues.append(ValidationIssue("warning", path_s, msg))

    def info(path_s: str, msg: str) -> None:
        issues.append(ValidationIssue("info", path_s, msg))

    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        err("/", f"XML ParseError: {exc}")
        return issues

    root = tree.getroot()
    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    if root_tag.lower() not in {t.lower() for t in KNOWN_ROOT_TAGS} and root_tag.lower() != "logger":
        # Manche Dateien starten direkt mit <protocols> unter einem Wrapper
        if root.find(".//protocol") is None and root.find(".//parameter") is None:
            err(root_tag, "Unbekanntes Root-Element und keine protocol/parameter-Kinder gefunden")
        else:
            warn(root_tag, f"Ungewöhnliches Root-Element '{root_tag}' (erwartet u.a. <logger>)")

    protocols = root.findall(".//protocol")
    if not protocols:
        # Manche modernen Defs nutzen logprotocol
        protocols = root.findall(".//logprotocol")
    if not protocols:
        warn("/", "Kein <protocol> / <logprotocol> gefunden – Parameter werden global gesucht")

    for proto in protocols:
        pid = proto.get("id") or proto.get("type") or "(unnamed)"
        ppath = f"protocol[@id='{pid}']"
        baud = proto.get("baud")
        if baud:
            try:
                b = int(baud)
                if b not in (4800, 9600, 10400, 38400, 500000, 0):
                    info(ppath, f"Ungewöhnliche Baudrate {b} (SSM typisch 4800)")
            except ValueError:
                warn(ppath, f"baud ist nicht numerisch: {baud!r}")
        if pid.upper() not in KNOWN_PROTOCOL_IDS and strict:
            info(ppath, f"Unbekannte protocol id '{pid}'")

    seen_param_ids: dict[str, str] = {}
    param_count = 0
    ecuparam_count = 0
    convertible = 0
    complex_expr = 0
    no_addr = 0
    derived = 0

    def check_conversion_block(parent: ET.Element, ppath: str) -> None:
        nonlocal convertible, complex_expr
        conversions = parent.findall("conversions")
        # sowohl <conversions><conversion/></conversions> als auch flache <conversion/>
        conv_els = parent.findall(".//conversion")
        if not conv_els:
            warn(ppath, "Keine <conversion> gefunden")
            return
        for conv in conv_els:
            expr = (conv.get("expr") or "").strip()
            units = conv.get("units") or conv.get("metric") or ""
            cpath = f"{ppath}/conversion"
            if not expr:
                err(cpath, "conversion ohne expr-Attribut")
                continue
            if not units and strict:
                warn(cpath, "conversion ohne units/metric")
            parsed = parse_expr(expr)
            if parsed is not None:
                scale, offset = parsed
                if scale == 0:
                    warn(cpath, f"expr ergibt scale=0: {expr!r}")
                else:
                    convertible += 1
            else:
                if COMPLEX_EXPR_HINT.search(expr):
                    complex_expr += 1
                    info(cpath, f"Komplexer Ausdruck (kein scale/offset): {expr!r}")
                else:
                    warn(cpath, f"expr nicht in scale/offset übersetzbar: {expr!r}")

            st = conv.get("storagetype")
            if st and st not in ("uint8", "uint16", "uint32", "int8", "int16", "float"):
                warn(cpath, f"Unbekannter storagetype '{st}'")

            fmt = conv.get("format")
            if fmt and not re.match(r"^0(\.0+)?$", fmt):
                info(cpath, f"Ungewöhnliches format '{fmt}'")

    def check_address_block(parent: ET.Element, ppath: str, require_ecu: bool = False) -> list[int]:
        nonlocal no_addr
        addrs: list[int] = []
        addr_els = parent.findall("address")
        if not addr_els and parent.find("depends") is None:
            # Fallback byte direkt unter parent
            if not parent.findall("byte"):
                err(ppath, "Weder <address> noch <depends> vorhanden")
                no_addr += 1
                return addrs

        for addr_el in addr_els:
            length_attr = addr_el.get("length")
            if length_attr is not None:
                try:
                    ln = int(length_attr)
                    if ln < 1 or ln > 4:
                        warn(f"{ppath}/address", f"ungewöhnliche length={ln}")
                except ValueError:
                    err(f"{ppath}/address", f"length nicht numerisch: {length_attr!r}")

            bit_attr = addr_el.get("bit")
            if bit_attr is not None:
                try:
                    bit = int(bit_attr)
                    if bit < 0 or bit > 31:
                        err(f"{ppath}/address", f"bit außerhalb 0..31: {bit}")
                except ValueError:
                    err(f"{ppath}/address", f"bit nicht numerisch: {bit_attr!r}")

            ecu_els = addr_el.findall("ecu")
            if require_ecu and not ecu_els:
                warn(f"{ppath}/address", "ecuparam ohne <ecu id=...> Unterblöcke")

            if ecu_els:
                for ecu_el in ecu_els:
                    eid = ecu_el.get("id")
                    if not eid:
                        err(f"{ppath}/address/ecu", "<ecu> ohne id-Attribut")
                        continue
                    if not ECU_ID_RE.match(eid):
                        warn(f"{ppath}/address/ecu[@id='{eid}']", "ECU-ID hat ungewöhnliches Format")
                    local = extract_byte_addresses(ecu_el)
                    if not local:
                        err(
                            f"{ppath}/address/ecu[@id='{eid}']",
                            "Keine gültige Adresse unter <ecu>",
                        )
                    for a in local:
                        if a < 0 or a > 0xFFFFFF:
                            err(
                                f"{ppath}/address/ecu[@id='{eid}']",
                                f"Adresse außerhalb 24-bit: 0x{a:X}",
                            )
                    addrs.extend(local)
            else:
                local = extract_byte_addresses(addr_el)
                if not local:
                    # Text könnte Müll sein
                    raw = (addr_el.text or "").strip()
                    if raw:
                        err(f"{ppath}/address", f"Ungültiges Adressformat: {raw!r}")
                    else:
                        err(f"{ppath}/address", "Leerer address-Block ohne <byte>/<ecu>")
                for a in local:
                    if a < 0 or a > 0xFFFFFF:
                        err(f"{ppath}/address", f"Adresse außerhalb 24-bit: 0x{a:X}")
                addrs.extend(local)

        if not addrs and parent.find("depends") is None:
            no_addr += 1
        return addrs

    # --- parameters ---
    for param in root.findall(".//parameter"):
        param_count += 1
        pid = param.get("id") or ""
        name = param.get("name") or ""
        ppath = element_path(param, root)

        if not pid and not name:
            err(ppath, "parameter ohne id und name")
        if pid:
            if pid in seen_param_ids:
                err(ppath, f"Doppelte parameter id '{pid}' (auch bei {seen_param_ids[pid]})")
            else:
                seen_param_ids[pid] = ppath

        # target / ecubit soft checks
        target = param.get("target")
        if target is not None and target not in ("1", "2", "3", "ECU", "TCU", "both"):
            info(ppath, f"Ungewöhnliches target='{target}'")

        ecubit = param.get("ecubit")
        if ecubit is not None:
            try:
                b = int(ecubit)
                if b < 0 or b > 7:
                    warn(ppath, f"ecubit außerhalb 0..7: {b}")
            except ValueError:
                warn(ppath, f"ecubit nicht numerisch: {ecubit!r}")

        if param.find("depends") is not None:
            derived += 1
            refs = param.findall("./depends/ref")
            if not refs:
                err(f"{ppath}/depends", "depends ohne <ref>")
            for ref in refs:
                if not ref.get("parameter") and not ref.get("ecuparam"):
                    err(f"{ppath}/depends/ref", "ref ohne parameter/ecuparam-Attribut")
            check_conversion_block(param, ppath)
            continue

        check_address_block(param, ppath, require_ecu=False)
        check_conversion_block(param, ppath)

    # --- ecuparams ---
    for ecuparam in root.findall(".//ecuparam"):
        ecuparam_count += 1
        pid = ecuparam.get("id") or ""
        name = ecuparam.get("name") or ""
        ppath = element_path(ecuparam, root)

        if not pid and not name:
            err(ppath, "ecuparam ohne id und name")
        if pid:
            key = f"ecu:{pid}"
            if key in seen_param_ids:
                err(ppath, f"Doppelte ecuparam id '{pid}'")
            else:
                seen_param_ids[key] = ppath

        check_address_block(ecuparam, ppath, require_ecu=True)
        check_conversion_block(ecuparam, ppath)

    # --- switches (soft) ---
    for sw in root.findall(".//switch"):
        spath = element_path(sw, root)
        if not sw.get("id") and not sw.get("name"):
            warn(spath, "switch ohne id/name")
        bit = sw.get("bit")
        if bit is not None:
            try:
                b = int(bit)
                if b < 0 or b > 7:
                    warn(spath, f"switch bit außerhalb 0..7: {b}")
            except ValueError:
                warn(spath, f"switch bit nicht numerisch: {bit!r}")

    # Summary infos
    info(
        "/",
        f"Statistik: parameters={param_count}, ecuparams={ecuparam_count}, "
        f"derived={derived}, convertible_exprs≈{convertible}, "
        f"complex_exprs≈{complex_expr}, missing_addr≈{no_addr}",
    )

    if param_count == 0 and ecuparam_count == 0:
        err("/", "Keine <parameter> oder <ecuparam> Elemente gefunden")

    if strict:
        # In strict mode: warnings zu fehlenden Units etc. bleiben warnings,
        # aber doppelte kritische Dinge sind bereits errors.
        pass

    return issues


def print_validation_report(issues: list[ValidationIssue]) -> int:
    """Druckt Report; Return-Code 0 ok, 1 bei errors, 2 bei warnings-only optional."""
    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]
    infos = [i for i in issues if i.level == "info"]

    for i in issues:
        stream = sys.stderr if i.level == "error" else sys.stdout
        print(str(i), file=stream)

    print(
        f"\nValidation summary: {len(errors)} error(s), "
        f"{len(warnings)} warning(s), {len(infos)} info"
    )
    if errors:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Parser / generator
# ---------------------------------------------------------------------------

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
        wanted |= set(ecu_ids)

    results: list[ParsedParam] = []

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

    if include_ecuparams:
        for ecuparam in root.findall(".//ecuparam"):
            name = ecuparam.get("name") or ecuparam.get("id") or "unknown"
            pid = ecuparam.get("id") or name

            addrs, matched = get_addresses_for_ecu(ecuparam, wanted)
            if not addrs:
                continue
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="RomRaider logger.xml → ssm2_parameters.h (mit ECU-Filter + Schema-Validierung)"
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
    ap.add_argument(
        "--validate-only",
        action="store_true",
        help="Nur Schema-/Struktur-Validierung, keinen Header schreiben",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Strengere Validierung (mehr Warnings bei ungewöhnlichen Attributen)",
    )
    ap.add_argument(
        "--skip-validate",
        action="store_true",
        help="Validierung vor dem Generieren überspringen",
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

    # Validation pass
    if args.validate_only or not args.skip_validate:
        issues = validate_logger_xml(args.xml, strict=args.strict)
        rc = print_validation_report(issues)
        if args.validate_only:
            return rc
        if rc != 0:
            print(
                "\nValidierung hat Fehler gemeldet – Generierung abgebrochen. "
                "Mit --skip-validate erzwingen.",
                file=sys.stderr,
            )
            return rc

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
