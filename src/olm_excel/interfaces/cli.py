"""Command-line entry point (W01 stub)."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from olm_excel import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="olm-excel", description="Convert OLM archives to Excel.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    convert = sub.add_parser("convert", help="convert one or more .olm files")
    convert.add_argument("inputs", nargs="+", help="paths to .olm files (read-only)")
    convert.add_argument("-o", "--output-dir", default=".", help="directory for workbooks")
    profile = sub.add_parser(
        "profile",
        help="write a structure-only report of an archive (no values); run it where the archive lives",
    )
    profile.add_argument("input", type=Path, help="path to the archive (read-only; any file name)")
    profile.add_argument("-o", "--output", type=Path, default=Path("olm-profile.json"), help="report path")
    profile.add_argument(
        "--show-names",
        action="store_true",
        help="keep real folder and file names instead of redacting them (may reveal account addresses)",
    )
    return parser


def _run_profile(args: argparse.Namespace) -> int:
    from olm_excel.core.profile import profile_archive

    def progress(n: int, total: int) -> None:
        if n == total or n % 500 == 0:
            print(f"\rprofiling member {n}/{total}", end="", file=sys.stderr, flush=True)

    report = profile_archive(args.input, reveal_names=args.show_names, progress=progress)
    print(file=sys.stderr)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if "error" in report:
        print(f"olm-excel: {report['error']}", file=sys.stderr)
        return 1
    totals = report["totals"]
    print(
        f"{report['input']['members']} members in {totals['member_groups']} groups; "
        f"{totals['xml_members_parsed']} XML members parsed; {totals['source_values']} source values counted."
    )
    print(f"Report written to {args.output}. It contains structure only: review it before sharing.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "profile":
        return _run_profile(args)
    if args.command == "convert":
        print("olm-excel: conversion is not implemented yet (W02-W05)", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
