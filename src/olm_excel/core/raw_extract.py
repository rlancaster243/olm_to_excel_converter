"""Raw extractor (W04, default-on, ADR-008).

Contract: docs/fidelity/04-CONTRACTS-AND-DATA.md, "Raw extract contract".
Writes one row per source value of each unclaimed XML member. Raw rows
state where a value sat, never what it means, and are never promoted to
family sheets.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from olm_excel.core.completeness import MemberAccount, Outcome, decide_outcome, manifest_rows
from olm_excel.core.errors import ConversionError, ErrorCode
from olm_excel.core.walker import WalkLimits, count_source_values, iter_source_values
from olm_excel.core.xlsx_writer import EXCEL_MAX_ROWS, Table, WorkbookWriter, chunk_utf16

__all__ = ["RAW_COLUMNS", "RAW_INDEX_COLUMNS", "RawExtractor", "XmlMember", "count_source_values", "write_raw_workbook"]

RAW_COLUMNS = (
    "raw_key",
    "archive_submission_id",
    "archive_member_path",
    "record_key",
    "element_path",
    "attribute",
    "text_position",
    "value_kind",
    "value",
    "chunk",
)
RAW_INDEX_COLUMNS = (
    "member_ordinal",
    "archive_member_path",
    "first_raw_key",
    "last_raw_key",
    "partitions",
    "source_values",
    "raw_written",
    "lost",
    "raw_complete",
    "stop_reason",
)

# Placeholder until measured on real archives (W08); configurable per run.
DEFAULT_MAX_VALUES = 5_000_000


@dataclass(frozen=True, slots=True)
class XmlMember:
    ordinal: int  # position in the archive inventory, used in raw_key
    path: str
    open: Callable[[], BinaryIO]


class RawExtractor:
    """Extract unclaimed XML members into raw sheets and account for every value.

    With ``enabled=False`` nothing is written, but every value is still
    counted and reported as lost (RAW_EXTRACT_DISABLED), so the outcome
    does not depend on the flag.
    """

    def __init__(
        self,
        writer: WorkbookWriter,
        *,
        submission_id: str,
        enabled: bool = True,
        max_values: int = DEFAULT_MAX_VALUES,
        limits: WalkLimits = WalkLimits(),
    ) -> None:
        self._submission_id = submission_id
        self._enabled = enabled
        self._remaining = max_values
        self._limits = limits
        self._index: Table | None = None
        self._raw: Table | None = None
        self._index_rows: list[Sequence[str]] = []
        if enabled:
            self._index = writer.add_table("_raw_index", RAW_INDEX_COLUMNS)
            self._raw = writer.add_table("raw", RAW_COLUMNS, partitioned=True)

    def extract(self, member: XmlMember) -> MemberAccount:
        account = MemberAccount(member.path)
        if not self._enabled:
            self._count_only(member, account, ErrorCode.RAW_EXTRACT_DISABLED)
            return account

        first_key = last_key = ""
        first_partition = 0
        stop: ErrorCode | None = None
        try:
            with member.open() as stream:
                for value in iter_source_values(stream, self._limits):
                    account.source_values += 1
                    if self._remaining <= 0:
                        stop = ErrorCode.RAW_EXTRACT_LIMIT
                        account.add_lost(ErrorCode.RAW_EXTRACT_LIMIT)
                        continue
                    raw_key = f"{member.ordinal}:{value.node_ordinal}"
                    position = "" if value.text_position is None else str(value.text_position)
                    if not first_key:
                        first_key = raw_key
                        first_partition = self._raw.next_row_partition()
                    for chunk_no, chunk in enumerate(chunk_utf16(value.value), start=1):
                        self._raw.append((
                            raw_key, self._submission_id, member.path, "", value.element_path,
                            value.attribute, position, value.value_kind, chunk, str(chunk_no),
                        ))
                    account.raw += 1
                    self._remaining -= 1
                    last_key = raw_key
        except ConversionError as exc:
            if exc.code is ErrorCode.EXCEL_LIMIT:
                raise
            account.mark_uncounted(exc.code)
            stop = exc.code
        partitions = self._raw.partition_names[first_partition:] if first_key else []
        self._index_rows.append((
            str(member.ordinal), member.path, first_key, last_key, " ".join(partitions),
            str(account.source_values) if account.counted else f"uncounted (>= {account.source_values})",
            str(account.raw), str(account.lost_total), str(stop is None).lower(), stop or "",
        ))
        return account

    def _count_only(self, member: XmlMember, account: MemberAccount, reason: ErrorCode) -> None:
        try:
            with member.open() as stream:
                for _ in iter_source_values(stream, self._limits):
                    account.source_values += 1
                    account.add_lost(reason)
        except ConversionError as exc:
            account.mark_uncounted(exc.code)

    def finish(self) -> None:
        """Write the raw index. Call once, after every member is extracted."""
        if self._index is not None:
            for row in self._index_rows:
                self._index.append(row)


def write_raw_workbook(
    members: Sequence[XmlMember],
    target: Path,
    *,
    submission_id: str,
    raw_extract: bool = True,
    max_values: int = DEFAULT_MAX_VALUES,
    max_rows: int = EXCEL_MAX_ROWS,
) -> tuple[Outcome, list[MemberAccount]]:
    """Convert archive members that no adapter claims (all of them, until W05).

    With no family converted the outcome is UNSUPPORTED by the 04 rule; the
    verified workbook is still published so it can be assessed (02 decision).
    """
    with WorkbookWriter(target, max_rows=max_rows) as writer:
        manifest = writer.add_table("_manifest", ("key", "value"))
        extractor = RawExtractor(writer, submission_id=submission_id, enabled=raw_extract, max_values=max_values)
        accounts = [extractor.extract(member) for member in members]
        extractor.finish()
        outcome = decide_outcome(accounts, families_converted=0)
        for row in manifest_rows(outcome, accounts, raw_extract=raw_extract):
            manifest.append(row)
        for account in accounts:
            manifest.append((f"member:{account.member_path}", _member_summary(account)))
    return outcome, accounts


def _member_summary(account: MemberAccount) -> str:
    lost = ",".join(f"{reason}={n}" for reason, n in sorted(account.lost.items()))
    counted = "counted" if account.counted else f"uncounted ({account.stop_reason})"
    return f"source_values={account.source_values} raw={account.raw} lost={account.lost_total} [{lost}] {counted}"
