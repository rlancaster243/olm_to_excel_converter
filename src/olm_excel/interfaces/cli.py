"""Command-line entry point: `convert` and `profile`."""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from collections.abc import Sequence
from pathlib import Path

from olm_excel import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="olm-excel", description="Convert OLM archives to Excel.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    convert = sub.add_parser("convert", help="convert one or more OLM archives to Excel workbooks")
    convert.add_argument("inputs", nargs="+", type=Path, help="archives to convert (opened read-only; any file name)")
    convert.add_argument("-o", "--output-dir", type=Path, default=Path("."), help="directory for workbooks (created if missing)")
    convert.add_argument(
        "--export-images",
        action="store_true",
        help="also write contact pictures as separate image files next to the workbook (default: metadata only, result is PARTIAL)",
    )
    convert.add_argument("--no-raw-extract", action="store_true", help="do not write unmapped values as raw rows (they are reported as lost) [ADR-008 PROPOSED]")
    convert.add_argument("--max-raw-values", "--raw-extract-max-values", dest="max_raw_values", type=int, default=None, help="cap on raw rows per archive (default 5000000, ADR-008 PROPOSED placeholder; legacy name --raw-extract-max-values)")
    convert.add_argument("--overwrite", action="store_true", help="replace an existing workbook of the same name")
    convert.add_argument("--max-member-gib", type=float, default=None, help="allow archive members up to this many GiB uncompressed (default 2)")
    convert.add_argument("--max-ratio", type=float, default=None, help="allow a compression ratio up to this per member (default 100)")
    convert.add_argument("--debug", action="store_true", help="show a traceback if something unexpected fails")
    audit = sub.add_parser(
        "audit-phones",
        help="test whether phone values are altered: compare the archive with a workbook (counts only, no values)",
    )
    audit.add_argument("archive", type=Path, help="the OLM archive (read-only)")
    audit.add_argument("--workbook", type=Path, default=None, help="a workbook to compare against; without it only the archive's phone shapes are counted")
    audit.add_argument("-o", "--output", type=Path, default=Path("phone-audit.json"), help="report path (aggregate counts only)")
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


def _run_audit_phones(args: argparse.Namespace) -> int:
    from olm_excel.core.errors import ConversionError
    from olm_excel.core.phone_audit import audit_phones

    def progress(n: int, total: int) -> None:
        if n == total or n % 500 == 0:
            print(f"\raudit member {n}/{total}", end="", file=sys.stderr, flush=True)

    try:
        report = audit_phones(args.archive, args.workbook, progress=progress)
    except ConversionError as exc:
        print(f"olm-excel: {exc}", file=sys.stderr)
        return 1
    print(file=sys.stderr)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    src = report["source"]
    ni = src["numeric_inference"]
    print(f"source: {src['phone_values']} phone values in {src['records']} contacts")
    print(f"  numeric inference would alter {ni['would_alter']} ({ni['would_alter_pct']}%): {ni['by_cause']}")
    print(f"  start with = + - @ : {src['shape_counts'].get('formula_prefix', 0)} ({src['formula_prefix_pct']}%)")
    for column, risk in src["risk_by_field"].items():
        if risk["would_alter"] or risk["formula_prefix"]:
            print(f"    {column}: {risk['values']} values, would alter {risk['would_alter']} ({risk['would_alter_pct']}%), start with = + - @ {risk['formula_prefix']} ({risk['formula_prefix_pct']}%)")
    exit_code = 0
    for label, part in (report.get("workbook") or {}).items():
        if part.get("sheet_missing"):
            print(f"{label}: sheet not found")
            exit_code = 5
            continue
        cells = part["cells"]
        print(f"{label}: exact {cells.get('exact', 0)} ({part['exact_pct_of_source_phone_values']}%); not exact: "
              + (", ".join(f"{k} {v}" for k, v in cells.items() if k != "exact") or "none"))
        if part["quote_prefix"]:
            print(f"  quote prefix: {part['quote_prefix']}")
        if any(k != "exact" for k in cells):
            exit_code = 5
    print(f"Report written to {args.output}. It contains counts only: review it before sharing.")
    return exit_code


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


EXIT_CODES = {"SUCCESS": 0, "PARTIAL": 3, "UNSUPPORTED": 4, "FAILED": 1}
_SEVERITY = ["SUCCESS", "PARTIAL", "UNSUPPORTED", "FAILED"]


def safe_stem(path: Path, taken: set[str]) -> str:
    """Output file stem from the input name: path-safe, never empty, unique within the batch."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._-")[:80] or "archive"
    unique, n = stem, 1
    while unique in taken:
        n += 1
        unique = f"{stem}-{n}"
    taken.add(unique)
    return unique


def _summary(name: str, result) -> list[str]:
    lines = [f"{name}: {result.outcome.value}"]
    if result.error is not None:
        lines.append(f"  error: {result.error}")
        return lines
    t = result.totals
    claimed = sum(1 for m in result.members if m.adapter_id)
    unsupported = sum(1 for m in result.members if m.account is None)
    lines += [
        f"  workbook: {result.workbook}",
        f"  source values: {t.source_values} = mapped {t.mapped} + structural {t.structural} + raw {t.raw} + lost {t.lost}",
        f"  members: {len(result.members)} ({claimed} converted by an adapter, {len(result.members) - claimed - unsupported} raw-extracted, {unsupported} unsupported)",
    ]
    if result.pictures_dir is not None:
        lines.append(f"  pictures: {result.pictures_written} files in {result.pictures_dir}")
    for reason, count in result.lost_by_reason.items():
        lines.append(f"  lost {reason}: {count}")
    for code, count in sorted(result.warnings_by_code.items()):
        lines.append(f"  warning {code}: {count}")
    if t.uncounted_members:
        lines.append(f"  members not fully counted: {t.uncounted_members}")
    if result.outcome.value != "SUCCESS":
        lines.append(f"  {result.notice or 'NOT FULLY CONVERTED.'}")
        lines.append("  See the _manifest, _members, _warnings and raw sheets before relying on this file.")
    lines.append(f"  time: {result.seconds:.1f}s")
    return lines


def _run_convert(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from olm_excel.core.archive_guard import ArchiveLimits
    from olm_excel.core.convert import ConvertOptions, convert_archive
    from olm_excel.core.raw_extract import DEFAULT_MAX_VALUES

    limits = ArchiveLimits()
    if args.max_member_gib is not None:
        limits = replace(limits, max_member_uncompressed=int(args.max_member_gib * 1024**3))
    if args.max_ratio is not None:
        limits = replace(limits, max_ratio=args.max_ratio)
    options = ConvertOptions(
        limits=limits,
        raw_extract=not args.no_raw_extract,
        export_images=args.export_images,
        overwrite=args.overwrite,
        max_raw_values=args.max_raw_values or DEFAULT_MAX_VALUES,
    )
    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"olm-excel: cannot create output directory: {type(exc).__name__}", file=sys.stderr)
        return 1

    def progress(n: int, total: int) -> None:
        if n == total or n % 500 == 0:
            print(f"\rmember {n}/{total}", end="", file=sys.stderr, flush=True)

    taken: set[str] = set()
    worst = "SUCCESS"
    for source in args.inputs:
        stem = safe_stem(source, taken)
        try:
            result = convert_archive(source, args.output_dir, stem, options, progress=progress)
        except Exception as exc:  # unexpected: report the type only, values may be in the message
            print(file=sys.stderr)
            print(f"{source.name}: FAILED\n  error: INTERNAL_ERROR: {type(exc).__name__}", file=sys.stderr)
            if args.debug:
                traceback.print_exc()
            worst = "FAILED"
            continue
        print(file=sys.stderr)
        print("\n".join(_summary(source.name, result)))
        if _SEVERITY.index(result.outcome.value) > _SEVERITY.index(worst):
            worst = result.outcome.value
    return EXIT_CODES[worst]


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit-phones":
        return _run_audit_phones(args)
    if args.command == "profile":
        return _run_profile(args)
    if args.command == "convert":
        return _run_convert(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
