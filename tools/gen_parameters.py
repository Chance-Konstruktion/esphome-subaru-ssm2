#!/usr/bin/env python3
"""
RomRaider logger.xml -> ssm2_parameters.h Generator
for esphome-subaru-ssm2

Usage:
  python tools/gen_parameters.py logger.xml --validate-only
  python tools/gen_parameters.py logger.xml --ecu A2WC420F
  python tools/gen_parameters.py logger.xml --ecu A2WC420F --all -o out.h
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from ssm2_xml_generate import generate_header, parse_logger_xml
from ssm2_xml_common import is_useful
from ssm2_xml_validate import print_validation_report, validate_logger_xml
from ssm2_xml_graph import export_graph


def main() -> int:
    ap = argparse.ArgumentParser(
        description="RomRaider logger.xml -> ssm2_parameters.h (ECU filter + validation)"
    )
    ap.add_argument("xml", type=Path, help="Path to logger.xml")
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
        help="Filter by ECU-ID (repeatable)",
    )
    ap.add_argument("--all", action="store_true", help="All parseable parameters")
    ap.add_argument("--no-ecuparam", action="store_true", help="Ignore ecuparam")
    ap.add_argument("--list-ecus", action="store_true", help="List ECU-IDs")
    ap.add_argument("--validate-only", action="store_true", help="Validate only")
    ap.add_argument("--strict", action="store_true", help="Stricter validation")
    ap.add_argument(
        "--skip-validate", action="store_true", help="Skip validation"
    )
    ap.add_argument(
        "--graph",
        choices=("mermaid", "dot", "ascii"),
        help="Export depends graph",
    )
    ap.add_argument("--graph-out", type=Path, help="Graph output file")
    ap.add_argument(
        "--graph-only", action="store_true", help="Only graph, no header"
    )
    ap.add_argument(
        "--graph-dir",
        choices=("LR", "RL", "TB", "BT"),
        help="Mermaid direction (default: auto)",
    )
    args = ap.parse_args()

    if not args.xml.exists():
        print(f"File not found: {args.xml}", file=sys.stderr)
        return 1

    if args.list_ecus:
        tree = ET.parse(args.xml)
        ecu_ids = {
            e.get("id") for e in tree.getroot().findall(".//ecu") if e.get("id")
        }
        if not ecu_ids:
            print('No <ecu id="..."> entries found.')
        else:
            print(f"ECU-IDs found ({len(ecu_ids)}):")
            for eid in sorted(ecu_ids):
                print(f"  {eid}")
        return 0

    if args.graph and args.graph_only:
        text = export_graph(
            args.xml, fmt=args.graph, out=args.graph_out, direction=args.graph_dir
        )
        if args.graph_out:
            print(
                f"Graph written -> {args.graph_out} ({args.graph})",
                file=sys.stderr,
            )
        else:
            sys.stdout.write(text)
        return 0

    if args.validate_only or not args.skip_validate:
        issues = validate_logger_xml(args.xml, strict=args.strict)
        rc = print_validation_report(issues)
        if args.validate_only:
            if args.graph:
                text = export_graph(
                    args.xml,
                    fmt=args.graph,
                    out=args.graph_out,
                    direction=args.graph_dir,
                )
                if args.graph_out:
                    print(
                        f"Graph written -> {args.graph_out} ({args.graph})",
                        file=sys.stderr,
                    )
                else:
                    sys.stdout.write(text)
            return rc
        if rc != 0:
            print(
                "Validation reported errors - generation aborted. "
                "Use --skip-validate to force.",
                file=sys.stderr,
            )
            return rc

    if args.graph:
        text = export_graph(
            args.xml, fmt=args.graph, out=args.graph_out, direction=args.graph_dir
        )
        if args.graph_out:
            print(
                f"Graph written -> {args.graph_out} ({args.graph})",
                file=sys.stderr,
            )

    params = parse_logger_xml(
        args.xml,
        ecu_ids=args.ecu_ids,
        include_ecuparams=not args.no_ecuparam,
    )
    if not args.all:
        params = [p for p in params if is_useful(p.name) or p.skip_reason]

    if not params:
        print("No usable parameters found.", file=sys.stderr)
        if args.ecu_ids:
            print("Hint: run with --list-ecus.", file=sys.stderr)
        return 1

    header = generate_header(params, str(args.xml), args.ecu_ids)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(header, encoding="utf-8")

    emitted = [p for p in params if not p.skip_reason]
    skipped = [p for p in params if p.skip_reason]
    print(
        f"Wrote {len(emitted)} parameters -> {args.output}"
        + (f" (skipped {len(skipped)})" if skipped else "")
    )
    if args.ecu_ids:
        print(f"ECU filter : {', '.join(args.ecu_ids)}")
    print()
    for p in params:
        flag = "SKIP" if p.skip_reason else "OK  "
        src = f"[{p.source}]"
        st = f" storage={p.storagetype}" if p.storagetype else ""
        print(
            f"  {flag} 0x{p.full_address:06X}  len={p.data_length}  "
            f"{p.name[:40]:40s}  scale={p.scale:g}  offset={p.offset:g}  "
            f"[{p.unit}]{st}  {src}"
        )
        if p.skip_reason:
            print(f"         reason: {p.skip_reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
