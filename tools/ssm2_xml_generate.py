#!/usr/bin/env python3
"""Parse RomRaider logger.xml and generate ssm2_parameters.h."""
from __future__ import annotations

from pathlib import Path

import xml.etree.ElementTree as ET

from ssm2_xml_common import (
    ParsedParam,
    get_addresses_for_ecu,
    is_useful,
    normalize_ecu_id,
    parse_expr,
    pick_conversion,
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
