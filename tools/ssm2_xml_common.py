#!/usr/bin/env python3
"""Shared helpers for RomRaider logger.xml tooling."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

EXPR_PATTERNS = [
    (re.compile(r"^\s*\(?\s*x\s*([+-])\s*([0-9.]+)\s*\)?\s*$", re.I), "offset"),
    (re.compile(r"^\s*x\s*/\s*([0-9.]+)\s*$", re.I), "div"),
    (re.compile(r"^\s*x\s*\*\s*([0-9.]+)\s*$", re.I), "mul"),
    (re.compile(r"^\s*\(?\s*x\s*([+-])\s*([0-9.]+)\s*\)?\s*/\s*([0-9.]+)\s*$", re.I), "offset_div"),
    (re.compile(r"^\s*x\s*\*\s*([0-9.]+)\s*/\s*([0-9.]+)\s*$", re.I), "mul_div"),
    (re.compile(r"^\s*x\s*$", re.I), "identity"),
]

COMPLEX_EXPR_HINT = re.compile(
    r"[a-zA-Z_][a-zA-Z0-9_]*|P\d+|\[|\]|GetLogParam|if\s*\(|\?", re.I
)

HEX_ADDR_RE = re.compile(r"^(0x)?[0-9a-fA-F]+$")
ECU_ID_RE = re.compile(r"^[0-9A-Za-z._-]{4,32}$")

PREFERRED_UNITS = {
    "c": 10, "°c": 10, "bar": 9, "rpm": 8, "%": 7,
    "v": 6, "g/s": 5, "°": 4, "deg": 4, "kpa": 3, "psi": 2,
}

USEFUL_NAMES = [
    "coolant", "engine speed", "rpm", "manifold", "boost",
    "intake air", "iat", "throttle", "tps", "accelerator",
    "battery", "mass air", "maf", "ignition", "timing",
    "knock", "iam", "wastegate", "fuel", "a/f", "afr",
    "oil temp", "vehicle speed", "load",
]

KNOWN_ROOT_TAGS = {"logger", "logprotocols", "protocols"}
KNOWN_PROTOCOL_IDS = {"SSM", "SSM2", "OBD", "ISO9141"}


@dataclass
class ParsedParam:
    name: str
    address: int
    full_address: int
    data_length: int
    scale: float
    offset: float
    unit: str
    is_signed: bool
    expr: str
    original_id: str
    source: str
    ecu_ids: list[str] = field(default_factory=list)


@dataclass
class ValidationIssue:
    level: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level.upper():7s}] {self.path}: {self.message}"


def parse_expr(expr: str) -> Optional[tuple[float, float]]:
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
            return 1.0 / div, (-val if sign == "-" else val) / div
        if kind == "mul_div":
            num, den = float(m.group(1)), float(m.group(2))
            if den == 0:
                return None
            return num / den, 0.0
    return None


def unit_score(units: str) -> int:
    return PREFERRED_UNITS.get(units.lower().replace("°", "").strip(), 0)


def is_useful(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in USEFUL_NAMES)


def normalize_ecu_id(ecu_id: str) -> str:
    return ecu_id.strip().upper().lstrip("0") or "0"


def element_path(el: ET.Element, root: ET.Element | None = None) -> str:
    tag = el.tag
    pid = el.get("id") or el.get("name")
    if pid:
        return f"{tag}[@id='{pid}']" if el.get("id") else f"{tag}[@name='{pid}']"
    return tag


def parse_address_token(text: str) -> Optional[int]:
    text = (text or "").strip()
    if not text or not HEX_ADDR_RE.match(text):
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
