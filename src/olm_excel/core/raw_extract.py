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
from olm_excel.core.walker import SourceValue, WalkLimits, count_source_values, iter_source_values
from olm_excel.core.xlsx_writer import EXCEL_MAX_ROWS, Table, WorkbookWriter, chunk_utf16

__all__ = [
    "RAW_COLUMNS",
    "RAW_INDEX_COLUMNS",
    "MemberRawState",
    "RawExtractor",
    "XmlMember",
    "count_source_values",
    "write_raw_workbook",
]

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


@dataclass(slots=True)
class MemberRawState:
    """Per-member bookkeeping for the raw index."""

    member: XmlMember
    first_key: str = ""
    last_key: str = ""
    first_partition: int = 0
    stop: ErrorCode | None = None


class RawExtractor:
    """Route source values nobody mapped to raw rows, and account for each one.

    Used for whole unclaimed XML members (``extract``) and for unknown fields
    inside claimed records (``begin_member`` / ``route`` / ``end_member``).
    With ``enabled=False`` nothing is written, but every value is still
    reported as lost (RAW_EXTRACT_DISABLED), so the outcome never depends on
    the flag.
    """

    def __init__(
        self,
        writer: WorkbookWriter,
        *,
        submission_id: str,
        enabled: bool = True,
        max_values: int = DEFAULT_MAX_VALUES,
        limits: WalkLimits = WalkLimits(),
        provenance=None,
    ) -> None:
        self._writer = writer
        self._submission_id = submission_id
        self._enabled = enabled
        self._remaining = max_values
        self._limits = limits
        self._provenance = provenance
        self._raw: Table | None = None  # created on the first raw row, so clean conversions have no raw sheets
        self._index_rows: list[Sequence[str]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def begin_member(self, member: XmlMember) -> MemberRawState:
        return MemberRawState(member)

    def _log(self, state: MemberRawState, value: SourceValue, status: str, detail: str = "") -> None:
        if self._provenance is not None:
            self._provenance.log(
                member_ordinal=state.member.ordinal,
                member_path=state.member.path,
                element_path=value.element_path,
                attribute=value.attribute,
                occurrence=value.node_ordinal,
                status=status,
                detail=detail or status,
                value=value.value,
            )

    def route(self, state: MemberRawState, value: SourceValue, account: MemberAccount, record_key: str = "") -> None:
        """Write one unmapped source value as raw rows, or count it as lost."""
        if not self._enabled:
            account.add_lost(ErrorCode.RAW_EXTRACT_DISABLED)
            self._log(state, value, f"lost:{ErrorCode.RAW_EXTRACT_DISABLED.value}", ErrorCode.RAW_EXTRACT_DISABLED.value)
            return
        if self._remaining <= 0:
            state.stop = ErrorCode.RAW_EXTRACT_LIMIT
            account.add_lost(ErrorCode.RAW_EXTRACT_LIMIT)
            self._log(state, value, f"lost:{ErrorCode.RAW_EXTRACT_LIMIT.value}", ErrorCode.RAW_EXTRACT_LIMIT.value)
            return
        if self._raw is None:
            self._raw = self._writer.add_table("raw", RAW_COLUMNS, partitioned=True)
        raw_key = f"{state.member.ordinal}:{value.node_ordinal}"
        position = "" if value.text_position is None else str(value.text_position)
        if not state.first_key:
            state.first_key = raw_key
            state.first_partition = self._raw.next_row_partition()
        for chunk_no, chunk in enumerate(chunk_utf16(value.value), start=1):
            self._raw.append((
                raw_key, self._submission_id, state.member.path, record_key, value.element_path,
                value.attribute, position, value.value_kind, chunk, str(chunk_no),
            ))
        account.raw += 1
        self._remaining -= 1
        state.last_key = raw_key
        self._log(state, value, "raw", raw_key)

    def end_member(
        self, state: MemberRawState, account: MemberAccount, stop: ErrorCode | None = None,
        *, force: bool = False,
    ) -> None:
        """Add the member's `_raw_index` row.

        Finding #14: unclaimed members always get a row when enabled, even when
        quiet (0 raw), so grain never drifts. Claimed members via MemberContext
        keep the old activity-gated behavior to avoid indexing clean conversions.
        """
        if not self._enabled:
            return
        stop = stop or state.stop
        if not force and not (state.first_key or stop or account.raw or account.lost_total):
            return
        partitions = (
            self._raw.partition_names[state.first_partition:]
            if (state.first_key and self._raw is not None)
            else []
        )
        self._index_rows.append((
            str(state.member.ordinal), state.member.path, state.first_key, state.last_key, " ".join(partitions),
            str(account.source_values) if account.counted else f"uncounted (>= {account.source_values})",
            str(account.raw), str(account.lost_total), str(stop is None).lower(), stop or "",
        ))

    def extract(self, member: XmlMember) -> MemberAccount:
        """Extract a whole unclaimed XML member: every value is routed to raw (or lost)."""
        account = MemberAccount(member.path)
        state = self.begin_member(member)
        stop: ErrorCode | None = None
        try:
            with member.open() as stream:
                for value in iter_source_values(stream, self._limits):
                    account.source_values += 1
                    self.route(state, value, account)
        except ConversionError as exc:
            if exc.code is ErrorCode.EXCEL_LIMIT:
                raise
            account.mark_uncounted(exc.code)
            stop = exc.code
        self.end_member(state, account, stop, force=True)
        return account

    def finish(self) -> None:
        """Write the raw index. Call once, after every member is processed."""
        if self._index_rows:
            index = self._writer.add_table("_raw_index", RAW_INDEX_COLUMNS)
            for row in self._index_rows:
                index.append(row)


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
