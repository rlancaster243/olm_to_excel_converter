"""Archive to workbook pipeline (W02 to W05).

archive guard -> discovery -> adapter or raw extractor -> workbook writer
-> verification -> atomic publication.

Nothing becomes visible at its final path until the workbook has been
re-read and checked: the workbook is written as ``<name>.xlsx.partial`` and the
optional picture directory as ``<stem>-pictures.partial``, and both are moved
into place only after verification. Output paths are never overwritten unless
``overwrite`` is set; an existing pictures directory is never replaced.
"""

from __future__ import annotations

import os
import shutil
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from olm_excel import __version__
from olm_excel.adapters import default_adapters
from olm_excel.core.archive_guard import ArchiveLimits, MemberInfo, SafeArchive
from olm_excel.core.completeness import MemberAccount, Outcome, Totals, decide_outcome, manifest_rows, outcome_notice, totals
from olm_excel.core.discovery import select_adapter, sniff_signature
from olm_excel.core.errors import ConversionError, ErrorCode
from olm_excel.core.member_context import MemberContext, StructuralStats, WarningLog
from olm_excel.core.raw_extract import DEFAULT_MAX_VALUES, RawExtractor, XmlMember
from olm_excel.core.walker import WalkLimits, iter_source_values
from olm_excel.core.xlsx_verify import verify_workbook
from olm_excel.core.xlsx_writer import WorkbookWriter

DEFAULT_MAX_PICTURE_BYTES = 128 * 1024**2
MEMBERS_HEADER = (
    "ordinal", "path", "kind", "adapter", "family", "source_values", "mapped", "structural", "raw", "lost",
    "counted", "stop_reason",
)
UNSUPPORTED_HEADER = ("ordinal", "path", "kind", "bytes", "reason")
WARNINGS_HEADER = ("member", "code", "detail", "count")
_XML_KINDS = ("xml", "xml-utf16")
_UNSUPPORTED_REASONS = {
    "encrypted": "encrypted member (U06): not read",
    "unreadable": "member could not be opened",
    "zip": "nested archive: listed, never opened",
    "binary-plist": "binary property list: no reader",
    "binary": "binary or non-XML content: no reader",
    "empty": "empty member",
}


@dataclass(frozen=True)
class ConvertOptions:
    raw_extract: bool = True
    export_images: bool = False
    overwrite: bool = False
    max_raw_values: int = DEFAULT_MAX_VALUES
    max_picture_bytes: int = DEFAULT_MAX_PICTURE_BYTES
    limits: ArchiveLimits = ArchiveLimits()
    walk_limits: WalkLimits = WalkLimits()


@dataclass
class MemberResult:
    ordinal: int
    path: str
    kind: str
    adapter_id: str = ""
    family: str = ""
    account: MemberAccount | None = None


@dataclass
class ConversionResult:
    outcome: Outcome
    workbook: Path | None = None
    pictures_dir: Path | None = None
    input_sha256: str = ""
    input_bytes: int = 0
    members: list[MemberResult] = field(default_factory=list)
    totals: Totals | None = None
    lost_by_reason: dict[str, int] = field(default_factory=dict)
    warnings_by_code: dict[str, int] = field(default_factory=dict)
    structural: dict[str, tuple[int, int]] = field(default_factory=dict)  # name -> (consumed, failed)
    pictures_written: int = 0
    notice: str = ""
    error: ConversionError | None = None
    seconds: float = 0.0


class PictureDirectory:
    """Content-addressed image files, written to a `.partial` directory and moved into place on commit."""

    def __init__(self, final: Path) -> None:
        self.final = final
        self.partial = final.with_name(final.name + ".partial")
        self.files = 0
        self._made = False
        self._committed = False

    def write(self, sha256: str, extension: str, data: bytes) -> str:
        if not self._made:
            self.partial.mkdir()
            self._made = True
        name = f"{sha256[:16]}.{extension}"
        path = self.partial / name
        if path.exists():
            if path.read_bytes() == data:
                return f"{self.final.name}/{name}"
            name = f"{sha256}.{extension}"  # first-16-hex collision: fall back to the full hash
            path = self.partial / name
            if path.exists():
                return f"{self.final.name}/{name}"
        with path.open("xb") as fh:
            fh.write(data)
        self.files += 1
        return f"{self.final.name}/{name}"

    def commit(self) -> None:
        if self._made:
            os.rename(self.partial, self.final)
            self._committed = True

    def rollback(self) -> None:
        """Undo ``commit`` after a later failure. Safe: the directory did not exist before this run."""
        if self._committed:
            shutil.rmtree(self.final, ignore_errors=True)
            self._committed = False

    def discard(self) -> None:
        if self._made and self.partial.exists():
            shutil.rmtree(self.partial, ignore_errors=True)


def _output_error(message: str) -> ConversionError:
    return ConversionError(ErrorCode.OUTPUT_IO, message, scope="workbook")


def convert_archive(
    source: Path,
    output_dir: Path,
    stem: str,
    options: ConvertOptions = ConvertOptions(),
    *,
    progress: Callable[[int, int], None] | None = None,
) -> ConversionResult:
    """Convert one archive. Returns FAILED (with ``error``) instead of raising for classified failures."""
    started = time.monotonic()
    try:
        result = _convert(Path(source), Path(output_dir), stem, options, progress)
    except ConversionError as exc:
        result = ConversionResult(Outcome.FAILED, error=exc)
    result.seconds = time.monotonic() - started
    return result


def _convert(source: Path, output_dir: Path, stem: str, options: ConvertOptions, progress) -> ConversionResult:
    target = output_dir / f"{stem}.xlsx"
    pictures = PictureDirectory(output_dir / f"{stem}-pictures") if options.export_images else None
    if target.exists() and not options.overwrite:
        raise _output_error("output workbook already exists (use overwrite to replace it)")
    if pictures is not None and (pictures.final.exists() or pictures.partial.exists()):
        raise _output_error("pictures directory already exists; remove or rename it first")
    if not output_dir.is_dir():
        raise _output_error("output directory does not exist")

    with SafeArchive.open(source, options.limits) as archive:
        adapters = default_adapters(pictures, options.max_picture_bytes)
        warnings = WarningLog()
        plan = _plan(archive, adapters, warnings)

        writer = WorkbookWriter(target)
        try:
            return _write(archive, plan, adapters, writer, pictures, source, options, warnings, progress)
        except BaseException:
            writer.abort()
            if pictures is not None:
                pictures.discard()
            raise


@dataclass
class _Planned:
    member: MemberInfo
    kind: str
    adapter: object | None


def _plan(archive: SafeArchive, adapters: list, warnings: WarningLog) -> list[_Planned]:
    plan: list[_Planned] = []
    for member in archive.inventory.members:
        kind = archive.sniff(member)
        adapter = None
        if kind in _XML_KINDS:
            try:
                with archive.open_member(member) as stream:
                    signature = sniff_signature(stream)
            except ConversionError:
                signature = None
            if signature is not None:
                adapter, results = select_adapter(signature, adapters)
                if adapter is None and sum(r.confident for r in results) > 1:
                    warnings.add(member.path, ErrorCode.AMBIGUOUS_ADAPTER, "more than one adapter matched; none was used")
        plan.append(_Planned(member, kind, adapter))
    return plan


def _write(archive, plan, adapters, writer, pictures, source, options, warnings, progress) -> ConversionResult:
    inventory = archive.inventory
    manifest = writer.add_table("_manifest", ("key", "value"))
    members_sheet = writer.add_table("_members", MEMBERS_HEADER, spill=True)
    warnings_sheet = writer.add_table("_warnings", WARNINGS_HEADER, spill=True)
    unsupported_sheet = writer.add_table("_unsupported", UNSUPPORTED_HEADER, spill=True)

    used = {id(p.adapter): p.adapter for p in plan if p.adapter is not None}
    for adapter in adapters:  # fixed order, only the adapters this archive needs
        if id(adapter) in used:
            adapter.prepare(writer)

    extractor = RawExtractor(
        writer,
        submission_id=inventory.sha256[:12],
        enabled=options.raw_extract,
        max_values=options.max_raw_values,
        limits=options.walk_limits,
    )
    stats = StructuralStats()
    results: list[MemberResult] = []
    unclaimed_non_xml = 0

    for n, planned in enumerate(plan, start=1):
        if progress:
            progress(n, len(plan))
        member = planned.member
        result = MemberResult(member.ordinal, member.path, planned.kind)
        results.append(result)
        if planned.kind not in _XML_KINDS:
            unclaimed_non_xml += 1
            reason = _UNSUPPORTED_REASONS.get(planned.kind, "no reader")
            unsupported_sheet.append((str(member.ordinal), member.path, planned.kind, str(member.size), reason))
            continue
        xml_member = XmlMember(member.ordinal, member.path, lambda m=member: archive.open_member(m))
        adapter = planned.adapter
        if adapter is None:
            result.account = extractor.extract(xml_member)
            continue
        result.adapter_id, result.family = adapter.adapter_id, adapter.family
        result.account = _convert_claimed(adapter, xml_member, extractor, stats, warnings, inventory.sha256[:12], options)
    extractor.finish()

    accounts = [r.account for r in results if r.account is not None]
    converted = sum(1 for r in results if r.adapter_id and r.account is not None and r.account.mapped > 0)
    outcome = decide_outcome(accounts, families_converted=converted, unclaimed_non_xml_members=unclaimed_non_xml)
    summary = totals(accounts)

    for r in results:
        a = r.account
        if a is None:
            continue
        members_sheet.append((
            str(r.ordinal), r.path, r.kind, r.adapter_id, r.family, str(a.source_values), str(a.mapped),
            str(a.structural), str(a.raw), str(a.lost_total), str(a.counted).lower(), a.stop_reason or "",
        ))
    for row in warnings.rows():
        warnings_sheet.append(row)

    lost = Counter()
    for a in accounts:
        lost.update(a.lost)
    structural = {name: (stats.consumed[name], stats.failed[name]) for name in sorted({*stats.consumed, *stats.failed})}
    warning_totals = warnings.totals_by_code()

    notice = outcome_notice(
        outcome,
        accounts,
        unclaimed_non_xml_members=unclaimed_non_xml,
        warning_codes=warning_totals,
        images_exported=options.export_images,
    )
    for row in manifest_rows(outcome, accounts, raw_extract=options.raw_extract, notice=notice):
        manifest.append(row)
    extra = [
        ("export_images", "on" if options.export_images else "off"),
        ("tool", f"olm-excel {__version__}"),
        ("input_file", source.name),
        ("input_sha256", inventory.sha256),
        ("input_bytes", str(inventory.size_bytes)),
        ("archive_members", str(len(inventory.members))),
    ]
    extra += [(f"adapter:{a.adapter_id}", a.adapter_version) for a in adapters if id(a) in used]
    extra += [(f"structural:{name}", f"consumed={c} failed={f}") for name, (c, f) in structural.items()]
    extra += [(f"lost:{reason}", str(count)) for reason, count in sorted(lost.items())]
    extra += [(f"warning:{code}", str(count)) for code, count in sorted(warning_totals.items())]
    if pictures is not None:
        extra.append(("pictures_exported", str(pictures.files)))
    extra += [(f"sheet:{name}", str(rows)) for name, rows in sorted(writer.sheet_rows.items()) if name != "_manifest"]
    for row in extra:
        manifest.append(row)

    writer.publish(
        lambda path: verify_workbook(path, writer.sheet_rows),
        commit=pictures.commit if pictures is not None else None,
        rollback=pictures.rollback if pictures is not None else None,
    )
    return ConversionResult(
        outcome,
        workbook=writer.target,
        pictures_dir=pictures.final if pictures is not None and pictures.files else None,
        input_sha256=inventory.sha256,
        input_bytes=inventory.size_bytes,
        members=results,
        totals=summary,
        lost_by_reason={str(k): v for k, v in sorted(lost.items())},
        warnings_by_code=dict(warning_totals),
        structural=structural,
        pictures_written=pictures.files if pictures is not None else 0,
        notice=notice,
    )


def _convert_claimed(adapter, member: XmlMember, extractor, stats, warnings, archive_id, options) -> MemberAccount:
    account = MemberAccount(member.path)
    ctx = MemberContext(
        member=member,
        account=account,
        extractor=extractor,
        allowed_structural=adapter.structural,
        stats=stats,
        warnings=warnings,
        archive_id=archive_id,
    )
    session = adapter.start(ctx)
    error: ConversionError | None = None
    try:
        with member.open() as stream:
            for value in ctx.values(iter_source_values(stream, options.walk_limits)):
                session.feed(value)
    except ConversionError as exc:
        if exc.code in (ErrorCode.EXCEL_LIMIT, ErrorCode.INTERNAL_ERROR):
            raise
        error = exc
    session.finish()
    ctx.finish(records_seen=session.records_seen, error=error)
    return account
