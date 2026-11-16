#!/usr/bin/env python3
"""Shared helpers for RomRaider logger.xml tooling."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

# scale, offset  where  eng = raw * scale + offset
EXPR_PATTERNS = [
    # x * a + b  /  x * a - b
    (re.compile(
        r"^\s*\(?\s*x\s*\*\s*([0-9.]+)\s*\)?\s*([+-])\s*([0-9.]+)\s*$", re.I
    ), "mul_offset"),
    # (x +/- a) / b
    (re.compile(
        r"^\s*\(\s*x\s*([+-])\s*([0-9.]+)\s*\)\s*/\s*([0-9.]+)\s*$", re.I
    ), "offset_div"),
    # (x +/- a)
    (re.compile(r"^\s*\(?\s*x\s*([+-])\s*([0-9.]+)\s*\)?\s*$", re.I), "offset"),
    # x / a
    (re.compile(r"^\s*x\s*/\s*([0-9.]+)\s*$", re.I), "div"),
    # x * a / b
    (re.compile(r"^\s*x\s*\*\s*([0-9.]+)\s*/\s*([0-9.]+)\s*$", re.I), "mul_div"),
    # x * a
    (re.compile(r"^\s*x\s*\*\s*([0-9.]+)\s*$", re.I), "mul"),
    # x
    (re.compile(r"^\s*x\s*$", re.I), "identity"),
]

COMPLEX_EXPR_HINT = re.compile(
    r"[a-zA-Z_][a-zA-Z0-9_]*|P\d+|\[|\]|GetLogParam|if\s*\(|\?", re.I
)

HEX_ADDR_RE = re.compile(r"^(0x)?[0-9a-fA-F]+$")
ECU_ID_RE = re.compile(r"^[0-9A-Za-z._-]{4,32}$")

SIGNED_STORAGE = {"int8", "int16", "int32"}
FLOAT_STORAGE = {"float", "float32", "single"}

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
KNOWN_PROTOCOL_IDS = {"SSM", "SSM2", "OBD", "ISO9141"}


@dataclass
class ParsedParam:
    name: str
    address: int  # table key: low byte (legacy) or full when < 0x100
    full_address: int  # last byte address (LSB of multi-byte span)
    base_address: int  # first byte address of the span
    data_length: int
    scale: float
    offset: float
    unit: str
    is_signed: bool
    is_float: bool
    storagetype: str
    expr: str
    original_id: str
    source: str
    ecu_ids: list[str] = field(default_factory=list)
    skip_reason: str = ""  # non-empty => do not emit into KNOWN_PARAMETERS


@dataclass
class ValidationIssue:
    level: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level.upper():7s}] {self.path}: {self.message}"


def parse_expr(expr: str) -> Optional[tuple[float, float]]:
    """Return (scale, offset) for eng = raw * scale + offset, or None."""
    expr = expr.strip()
    for pat, kind in EXPR_PATTERNS:
        m = pat.match(expr)
        if not m:
            continue
        if kind == "identity":
            return 1.0, 0.0
        if kind == "offset":
            sign, val = m.group(1), float(m.group(2))
            # eng = x + val  or  x - val  => scale=1, offset=+val or -val
            return 1.0, (val if sign == "+" else -val)
        if kind == "div":
            denom = float(m.group(1))
            if denom == 0:
                return None
            return 1.0 / denom, 0.0
        if kind == "mul":
            return float(m.group(1)), 0.0
        if kind == "offset_div":
            # (x +/- a) / b  => scale=1/b, offset=(+/-a)/b
            sign, val, div = m.group(1), float(m.group(2)), float(m.group(3))
            if div == 0:
                return None
            off = (val if sign == "+" else -val) / div
            return 1.0 / div, off
        if kind == "mul_div":
            num, den = float(m.group(1)), float(m.group(2))
            if den == 0:
                return None
            return num / den, 0.0
        if kind == "mul_offset":
            # x * a +/- b
            a, sign, b = float(m.group(1)), m.group(2), float(m.group(3))
            return a, (b if sign == "+" else -b)
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
    """Addresses from element text and child <byte> elements."""
    addrs: list[int] = []
    text = (container.text or "").strip()
    if text:
        # allow whitespace / comma separated tokens
        for part in re.split(r"[\s,;]+", text):
            if not part:
                continue
            val = parse_address_token(part)
            if val is not None:
                addrs.append(val)
    for byte_el in container.findall("byte"):
        t = (byte_el.text or "").strip()
        if t:
            val = parse_address_token(t)
            if val is not None:
                addrs.append(val)
    return addrs


def _length_attr(el: ET.Element) -> Optional[int]:
    raw = el.get("length")
    if raw is None:
        return None
    try:
        n = int(raw)
        return n if 1 <= n <= 8 else None
    except ValueError:
        return None


def _expand_length(addrs: list[int], length: Optional[int]) -> list[int]:
    """If a single base address carries length=N, expand to N consecutive bytes."""
    if length is None or length <= 1 or len(addrs) != 1:
        return addrs
    base = addrs[0]
    return [base + i for i in range(length)]


def get_addresses_for_ecu(
    param_el: ET.Element, wanted_ecu_ids: set[str] | None
) -> tuple[list[int], list[str]]:
    """
    Collect 24-bit addresses for a parameter/ecuparam.

    Supports RomRaider layouts:

    1) <address [length=N]>0x.. / <byte>…
         optional <ecu id="…"> children with nested bytes
    2) <ecu id="…"><address [length=N]>…</address></ecu>
       (common on <ecuparam>)
    3) direct <byte> under the parameter
    """
    matched_ecus: list[str] = []
    addrs: list[int] = []

    # --- Layout 1: <address> … </address> ---
    for addr_el in param_el.findall("address"):
        length = _length_attr(addr_el)
        ecu_children = list(addr_el.findall("ecu"))
        if not ecu_children:
            direct = _expand_length(extract_byte_addresses(addr_el), length)
            addrs.extend(direct)
            continue
        for ecu_el in ecu_children:
            ecu_id = ecu_el.get("id") or ""
            if not ecu_id:
                continue
            norm = normalize_ecu_id(ecu_id)
            if wanted_ecu_ids is None or norm in wanted_ecu_ids or ecu_id in wanted_ecu_ids:
                matched_ecus.append(ecu_id)
                local_len = _length_attr(ecu_el) or length
                addrs.extend(
                    _expand_length(extract_byte_addresses(ecu_el), local_len)
                )

    # --- Layout 2: <ecu id> <address>…  (and nested bytes) ---
    for ecu_el in param_el.findall("ecu"):
        ecu_id = ecu_el.get("id") or ""
        if not ecu_id:
            continue
        norm = normalize_ecu_id(ecu_id)
        if wanted_ecu_ids is not None and norm not in wanted_ecu_ids and ecu_id not in wanted_ecu_ids:
            continue
        matched_ecus.append(ecu_id)
        # addresses under this ecu
        for addr_el in ecu_el.findall("address"):
            length = _length_attr(addr_el)
            addrs.extend(_expand_length(extract_byte_addresses(addr_el), length))
        # bare bytes under ecu
        bare = extract_byte_addresses(ecu_el)
        # extract_byte_addresses also reads ecu text; avoid double-count if only nested address text
        # Prefer explicit address children; if none, use bare bytes
        if not ecu_el.findall("address"):
            addrs.extend(bare)

    # --- Layout 3: top-level <byte> ---
    if not addrs:
        addrs.extend(extract_byte_addresses(param_el))

    # unique, stable order
    seen: set[int] = set()
    ordered: list[int] = []
    for a in addrs:
        if a not in seen:
            seen.add(a)
            ordered.append(a)
    return ordered, matched_ecus


def pick_conversion(
    param_el: ET.Element,
) -> Optional[tuple[str, str, str]]:
    """
    Pick best conversion: (units, expr, storagetype).
    Prefer metric-ish units via unit_score.
    """
    candidates = []
    for conv in param_el.findall(".//conversion"):
        units = conv.get("units") or conv.get("metric") or ""
        expr = (conv.get("expr") or "").strip()
        st = (conv.get("storagetype") or "").strip().lower()
        if expr:
            candidates.append((unit_score(units), units, expr, st))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, units, expr, st = candidates[0]
    return units, expr, st


def signed_from_storage(storagetype: str) -> bool:
    """Signed only from storagetype – never from parameter name."""
    return storagetype.lower() in SIGNED_STORAGE


def is_float_storage(storagetype: str) -> bool:
    return storagetype.lower() in FLOAT_STORAGE


def cpp_float_literal(value: float) -> str:
    """
    Emit a valid C++ float literal with decimal point.
    1 -> 1.0f, -40 -> -40.0f, 0.25 -> 0.25f
    """
    if value != value:  # NaN
        return "0.0f /* NaN */"
    s = f"{value:.10g}"
    if "e" in s or "E" in s:
        # scientific – ensure decimal form when possible
        s = f"{value:.10e}"
    if "." not in s and "e" not in s and "E" not in s:
        s = s + ".0"
    return s + "f"
