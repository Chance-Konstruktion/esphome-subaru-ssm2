#!/usr/bin/env python3
"""
RomRaider logger.xml → ssm2_parameters.h Generator
für esphome-subaru-ssm2

Usage:
  python tools/gen_parameters.py logger.xml --validate-only
  python tools/gen_parameters.py logger.xml --ecu 2F12785606
  python tools/gen_parameters.py logger.xml --list-ecus
  python tools/gen_parameters.py logger.xml --graph mermaid --graph-out depends.md
  python tools/gen_parameters.py logger.xml --graph dot --graph-out depends.dot --graph-only
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Allow "python tools/gen_parameters.py" by putting tools/ on sys.path
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from ssm2_xml_generate import generate_header, parse_logger_xml
from ssm2_xml_common import is_useful
from ssm2_xml_validate import print_validation_report, validate_logger_xml
from ssm2_xml_graph import export_graph


def main() -> int:
    ap = argparse.ArgumentParser(
        description="RomRaider logger.xml → ssm2_parameters.h (ECU-Filter + Schema-Validierung)"
    )
    ap.add_argument("xml", type=Path, help="Pfad zur logger.xml")
    ap.add_argument(
        "-o", "--output", type=Path,
        default=Path("components/subaru_ssm2/ssm2_parameters.h"),
    )
    ap.add_argument(
        "--ecu", action="append", dest="ecu_ids", metavar="ECU_ID",
        help="ECU-ID filtern (mehrfach möglich)",
    )
    ap.add_argument("--all", action="store_true", help="Alle parsebaren Parameter")
    ap.add_argument("--no-ecuparam", action="store_true", help="ecuparam ignorieren")
    ap.add_argument("--list-ecus", action="store_true", help="ECU-IDs auflisten")
    ap.add_argument("--validate-only", action="store_true", help="Nur validieren")
    ap.add_argument("--strict", action="store_true", help="Strengere Validierung")
    ap.add_argument("--skip-validate", action="store_true", help="Validierung überspringen")
    ap.add_argument(
        "--graph",
        choices=("mermaid", "dot", "ascii"),
        help="Depends-Graph exportieren (mermaid|dot|ascii)",
    )
    ap.add_argument(
        "--graph-out",
        type=Path,
        help="Zieldatei für --graph (default: stdout)",
    )
    ap.add_argument(
        "--graph-only",
        action="store_true",
        help="Nur Graph erzeugen, kein Header / keine Validierungspflicht",
    )
    args = ap.parse_args()

    if not args.xml.exists():
        print(f"Datei nicht gefunden: {args.xml}", file=sys.stderr)
        return 1

    if args.list_ecus:
        tree = ET.parse(args.xml)
        ecu_ids = {e.get("id") for e in tree.getroot().findall(".//ecu") if e.get("id")}
        if not ecu_ids:
            print('Keine <ecu id="..."> Einträge gefunden.')
        else:
            print(f"Gefundene ECU-IDs ({len(ecu_ids)}):")
            for eid in sorted(ecu_ids):
                print(f"  {eid}")
        return 0

    if args.graph and args.graph_only:
        text = export_graph(args.xml, fmt=args.graph, out=args.graph_out)
        if args.graph_out:
            print(f"Graph geschrieben → {args.graph_out} ({args.graph})", file=sys.stderr)
        else:
            sys.stdout.write(text)
        return 0

    if args.validate_only or not args.skip_validate:
        issues = validate_logger_xml(args.xml, strict=args.strict)
        rc = print_validation_report(issues)
        if args.validate_only:
            if args.graph:
                text = export_graph(args.xml, fmt=args.graph, out=args.graph_out)
                if args.graph_out:
                    print(f"Graph geschrieben → {args.graph_out} ({args.graph})", file=sys.stderr)
                else:
                    sys.stdout.write(text)
            return rc
        if rc != 0:
            print(
                "\nValidierung hat Fehler gemeldet – Generierung abgebrochen. "
                "Mit --skip-validate erzwingen.",
                file=sys.stderr,
            )
            return rc

    if args.graph:
        text = export_graph(args.xml, fmt=args.graph, out=args.graph_out)
        if args.graph_out:
            print(f"Graph geschrieben → {args.graph_out} ({args.graph})", file=sys.stderr)
        else:
            # avoid mixing graph with parameter listing on stdout when generating header
            if args.graph_only or args.validate_only:
                sys.stdout.write(text)

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
            print("Tipp: --list-ecus ausführen.", file=sys.stderr)
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
