#!/usr/bin/env python3
"""Parse RomRaider logger.xml and generate ssm2_parameters.h."""
from __future__ import annotations

import sys
from pathlib import Path

import xml.etree.ElementTree as ET

from ssm2_xml_common import (
    ParsedParam,
    cpp_float_literal,
    get_addresses_for_ecu,
    is_float_storage,
    is_useful,
    normalize_ecu_id,
    parse_expr,
    pick_conversion,
    signed_from_storage,
)


def _build_param(
    name: str,
    pid: str,
    addrs: list[int],
    units: str,
    expr: str,
    storagetype: str,
    source: str,
    matched_ecus: list[str],
) -> ParsedParam | None:
    if not addrs:
        return None

    is_float = is_float_storage(storagetype)
    is_signed = signed_from_storage(storagetype)

    data_length = len(addrs)
    base_addr = min(addrs)
    # Table address = least-significant (last) byte of the span — matches subaru_ssm2.cpp
    full_addr = max(addrs)
    low_byte = full_addr & 0xFF

    parsed = parse_expr(expr)
    if parsed is None and not is_float:
        print(
            f"SKIP unparsed expr id={pid!r} name={name!r} expr={expr!r}",
            file=sys.stderr,
        )
        return None
    scale, offset = parsed if parsed is not None else (1.0, 0.0)

    skip_reason = ""
    if is_float:
        skip_reason = (
            f"float storagetype ({data_length} bytes @ 0x{base_addr:06X}) – "
            f"runtime has no binary32 path; refusing silent low-byte truncate"
        )
    elif base_addr > 0xFF or full_addr > 0xFF:
        skip_reason = (
            f"24-bit address 0x{base_addr:06X}..0x{full_addr:06X} – "
            f"runtime map is still uint8_t low-byte only"
        )

    return ParsedParam(
        name=name,
        address=low_byte,
        full_address=full_addr,
        base_address=base_addr,
        data_length=data_length,
        scale=scale,
        offset=offset,
        unit=units,
        is_signed=is_signed,
        is_float=is_float,
        storagetype=storagetype,
        expr=expr,
        original_id=pid,
        source=source,
        ecu_ids=list(matched_ecus),
        skip_reason=skip_reason,
    )


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

        # Global parameters: no ECU filter on address blocks
        addrs, _ = get_addresses_for_ecu(param, None)
        if not addrs:
            continue

        conv = pick_conversion(param)
        if not conv:
            continue
        units, expr, storagetype = conv

        p = _build_param(
            name, pid, addrs, units, expr, storagetype, "parameter", []
        )
        if p:
            results.append(p)

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
            units, expr, storagetype = conv

            p = _build_param(
                name, pid, addrs, units, expr, storagetype, "ecuparam", matched
            )
            if p:
                results.append(p)

    # Deduplicate by full 24-bit table address (LSB of span).
    # Also report low-byte collisions among *emittable* params.
    by_full: dict[int, ParsedParam] = {}
    for p in results:
        key = p.full_address
        if key not in by_full:
            by_full[key] = p
            continue
        existing = by_full[key]
        # Prefer ecuparam when filtering by ECU; else prefer useful names
        if p.source == "ecuparam" and existing.source == "parameter" and wanted:
            by_full[key] = p
        elif is_useful(p.name) and not is_useful(existing.name):
            by_full[key] = p

    merged = list(by_full.values())

    # Low-byte collision report (only among non-skipped)
    low_map: dict[int, list[ParsedParam]] = {}
    for p in merged:
        if p.skip_reason:
            continue
        low_map.setdefault(p.address, []).append(p)
    for low, group in sorted(low_map.items()):
        if len(group) > 1:
            ids = ", ".join(f"{g.original_id}@0x{g.full_address:06X}" for g in group)
            print(
                f"WARN low-byte collision 0x{low:02X}: {ids}",
                file=sys.stderr,
            )

    for p in merged:
        if p.skip_reason:
            print(
                f"SKIP {p.original_id} ({p.name}): {p.skip_reason}",
                file=sys.stderr,
            )

    return sorted(merged, key=lambda x: (x.base_address, x.full_address))


def generate_header(
    params: list[ParsedParam], source: str, ecu_ids: list[str] | None
) -> str:
    """Emit only non-skipped params into the legacy uint8_t map."""
    emit = [p for p in params if not p.skip_reason]
    skipped = [p for p in params if p.skip_reason]

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
        "//",
        "// Table address = least-significant byte of the multi-byte span",
        "// (see subaru_ssm2.cpp send_request_).",
    ]
    if skipped:
        lines.append(
            f"// Skipped entries (float or 24-bit address): {len(skipped)} – see generator log"
        )
    lines += [
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

    for p in sorted(emit, key=lambda x: x.address):
        unit_c = f'"{p.unit}"' if p.unit else "nullptr"
        name_c = p.name.replace("\\", "\\\\").replace('"', '\\"')
        comment_parts = []
        if p.ecu_ids:
            comment_parts.append(f"ECU: {', '.join(p.ecu_ids)}")
        if p.full_address > 0xFF or p.data_length > 1:
            comment_parts.append(
                f"full=0x{p.full_address:06X} base=0x{p.base_address:06X} len={p.data_length}"
            )
        if p.storagetype:
            comment_parts.append(f"storage={p.storagetype}")
        comment = f"  // {' | '.join(comment_parts)}" if comment_parts else ""
        scale_l = cpp_float_literal(p.scale)
        offset_l = cpp_float_literal(p.offset)
        lines.append(
            f'    {{0x{p.address:02X}, {{0x{p.address:02X}, "{name_c}", {unit_c}, '
            f"{scale_l}, {offset_l}, {p.data_length}, "
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
