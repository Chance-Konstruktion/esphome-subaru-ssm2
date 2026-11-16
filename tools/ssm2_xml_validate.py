#!/usr/bin/env python3
"""RomRaider logger.xml validation incl. ref existence and depends cycles."""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from ssm2_xml_common import (
    COMPLEX_EXPR_HINT,
    ECU_ID_RE,
    KNOWN_PROTOCOL_IDS,
    KNOWN_ROOT_TAGS,
    ValidationIssue,
    element_path,
    extract_byte_addresses,
    parse_expr,
)


def validate_logger_xml(path: Path, strict: bool = False) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def err(p: str, m: str) -> None:
        issues.append(ValidationIssue("error", p, m))

    def warn(p: str, m: str) -> None:
        issues.append(ValidationIssue("warning", p, m))

    def info(p: str, m: str) -> None:
        issues.append(ValidationIssue("info", p, m))

    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        err("/", f"XML ParseError: {exc}")
        return issues

    root = tree.getroot()
    root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if root_tag.lower() not in {t.lower() for t in KNOWN_ROOT_TAGS}:
        if root.find(".//protocol") is None and root.find(".//parameter") is None:
            err(root_tag, "Unbekanntes Root und keine protocol/parameter-Kinder")
        else:
            warn(root_tag, f"Ungewöhnliches Root-Element '{root_tag}'")

    protocols = root.findall(".//protocol") or root.findall(".//logprotocol")
    if not protocols:
        warn("/", "Kein <protocol>/<logprotocol> – Parameter global gesucht")
    for proto in protocols:
        pid = proto.get("id") or proto.get("type") or "(unnamed)"
        ppath = f"protocol[@id='{pid}']"
        baud = proto.get("baud")
        if baud:
            try:
                b = int(baud)
                if b not in (4800, 9600, 10400, 38400, 500000, 0):
                    info(ppath, f"Ungewöhnliche Baudrate {b}")
            except ValueError:
                warn(ppath, f"baud nicht numerisch: {baud!r}")
        if strict and pid.upper() not in KNOWN_PROTOCOL_IDS:
            info(ppath, f"Unbekannte protocol id '{pid}'")

    known_param_ids: set[str] = set()
    known_ecuparam_ids: set[str] = set()
    param_name_to_id: dict[str, str] = {}
    ecuparam_name_to_id: dict[str, str] = {}
    for param in root.findall(".//parameter"):
        pid = (param.get("id") or "").strip()
        pname = (param.get("name") or "").strip()
        if pid:
            known_param_ids.add(pid)
            if pname and pname not in param_name_to_id:
                param_name_to_id[pname] = pid
        elif pname:
            known_param_ids.add(pname)
            param_name_to_id[pname] = pname
    for ecuparam in root.findall(".//ecuparam"):
        pid = (ecuparam.get("id") or "").strip()
        pname = (ecuparam.get("name") or "").strip()
        if pid:
            known_ecuparam_ids.add(pid)
            if pname and pname not in ecuparam_name_to_id:
                ecuparam_name_to_id[pname] = pid
        elif pname:
            known_ecuparam_ids.add(pname)
            ecuparam_name_to_id[pname] = pname

    seen_param_ids: dict[str, str] = {}
    param_count = ecuparam_count = convertible = complex_expr = no_addr = derived = 0
    unresolved_refs = self_refs = 0
    derived_deps: dict[str, set[str]] = {}

    def check_conversion_block(parent: ET.Element, ppath: str) -> None:
        nonlocal convertible, complex_expr
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
                scale, _ = parsed
                if scale == 0:
                    warn(cpath, f"expr ergibt scale=0: {expr!r}")
                else:
                    convertible += 1
            elif COMPLEX_EXPR_HINT.search(expr):
                complex_expr += 1
                info(cpath, f"Komplexer Ausdruck (kein scale/offset): {expr!r}")
            else:
                warn(cpath, f"expr nicht in scale/offset übersetzbar: {expr!r}")
            st = conv.get("storagetype")
            if st and st not in ("uint8", "uint16", "uint32", "int8", "int16", "float"):
                warn(cpath, f"Unbekannter storagetype '{st}'")

    def check_address_block(parent: ET.Element, ppath: str, require_ecu: bool = False) -> None:
        nonlocal no_addr
        addr_els = parent.findall("address")
        if not addr_els and parent.find("depends") is None and not parent.findall("byte"):
            err(ppath, "Weder <address> noch <depends> vorhanden")
            no_addr += 1
            return
        addrs: list[int] = []
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
                        warn(f"{ppath}/address/ecu[@id='{eid}']", "ECU-ID ungewöhnliches Format")
                    local = extract_byte_addresses(ecu_el)
                    if not local:
                        err(f"{ppath}/address/ecu[@id='{eid}']", "Keine gültige Adresse unter <ecu>")
                    for a in local:
                        if a < 0 or a > 0xFFFFFF:
                            err(f"{ppath}/address/ecu[@id='{eid}']", f"Adresse außerhalb 24-bit: 0x{a:X}")
                    addrs.extend(local)
            else:
                local = extract_byte_addresses(addr_el)
                if not local:
                    raw = (addr_el.text or "").strip()
                    err(f"{ppath}/address", f"Ungültiges Adressformat: {raw!r}" if raw else "Leerer address-Block")
                for a in local:
                    if a < 0 or a > 0xFFFFFF:
                        err(f"{ppath}/address", f"Adresse außerhalb 24-bit: 0x{a:X}")
                addrs.extend(local)
        if not addrs and parent.find("depends") is None:
            no_addr += 1

    for param in root.findall(".//parameter"):
        param_count += 1
        pid = param.get("id") or ""
        name = param.get("name") or ""
        ppath = element_path(param)
        if not pid and not name:
            err(ppath, "parameter ohne id und name")
        if pid:
            if pid in seen_param_ids:
                err(ppath, f"Doppelte parameter id '{pid}' (auch bei {seen_param_ids[pid]})")
            else:
                seen_param_ids[pid] = ppath
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
            dep_ids: set[str] = set()
            for ref in refs:
                ref_param = (ref.get("parameter") or "").strip()
                ref_ecu = (ref.get("ecuparam") or "").strip()
                rpath = f"{ppath}/depends/ref"
                if not ref_param and not ref_ecu:
                    err(rpath, "ref ohne parameter/ecuparam-Attribut")
                    continue
                if ref_param:
                    resolved = ref_param
                    if ref_param not in known_param_ids:
                        alt = param_name_to_id.get(ref_param)
                        if alt:
                            resolved = alt
                            info(rpath, f"ref parameter='{ref_param}' über name → id '{alt}'")
                        else:
                            err(rpath, f"ref parameter='{ref_param}' existiert nicht")
                            unresolved_refs += 1
                            continue
                    if pid and resolved == pid:
                        err(rpath, f"Selbst-Referenz auf parameter '{pid}'")
                        self_refs += 1
                    dep_ids.add(resolved)
                if ref_ecu:
                    if ref_ecu not in known_ecuparam_ids:
                        alt = ecuparam_name_to_id.get(ref_ecu)
                        if alt:
                            info(rpath, f"ref ecuparam='{ref_ecu}' über name → id '{alt}'")
                        else:
                            err(rpath, f"ref ecuparam='{ref_ecu}' existiert nicht")
                            unresolved_refs += 1
            if pid:
                derived_deps[pid] = dep_ids
            check_conversion_block(param, ppath)
            continue

        check_address_block(param, ppath, require_ecu=False)
        check_conversion_block(param, ppath)

    for ecuparam in root.findall(".//ecuparam"):
        ecuparam_count += 1
        pid = ecuparam.get("id") or ""
        name = ecuparam.get("name") or ""
        ppath = element_path(ecuparam)
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

    for sw in root.findall(".//switch"):
        spath = element_path(sw)
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

    def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in graph}
        cycles: list[list[str]] = []
        stack: list[str] = []

        def dfs(node: str) -> None:
            color[node] = GRAY
            stack.append(node)
            for nxt in graph.get(node, ()):
                if nxt not in color:
                    continue
                if color[nxt] == GRAY:
                    try:
                        i = stack.index(nxt)
                        cycles.append(stack[i:] + [nxt])
                    except ValueError:
                        cycles.append([nxt, node, nxt])
                elif color[nxt] == WHITE:
                    dfs(nxt)
            stack.pop()
            color[node] = BLACK

        for n in list(graph):
            if color.get(n, BLACK) == WHITE:
                dfs(n)
        return cycles

    cycles = find_cycles(derived_deps)
    for cyc in cycles:
        err("/", "Zyklen in depends-Graph: " + " → ".join(cyc))

    info(
        "/",
        f"Statistik: parameters={param_count}, ecuparams={ecuparam_count}, "
        f"derived={derived}, convertible_exprs≈{convertible}, "
        f"complex_exprs≈{complex_expr}, missing_addr≈{no_addr}, "
        f"unresolved_refs={unresolved_refs}, self_refs={self_refs}, "
        f"dep_cycles={len(cycles)}",
    )
    if param_count == 0 and ecuparam_count == 0:
        err("/", "Keine <parameter> oder <ecuparam> Elemente gefunden")
    return issues


def print_validation_report(issues: list[ValidationIssue]) -> int:
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
    return 1 if errors else 0
