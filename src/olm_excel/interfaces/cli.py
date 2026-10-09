"""Command-line entry point (W01 stub)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from olm_excel import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="olm-excel", description="Convert OLM archives to Excel.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    convert = sub.add_parser("convert", help="convert one or more .olm files")
    convert.add_argument("inputs", nargs="+", help="paths to .olm files (read-only)")
    convert.add_argument("-o", "--output-dir", default=".", help="directory for workbooks")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "convert":
        print("olm-excel: conversion is not implemented yet (W02-W05)", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
