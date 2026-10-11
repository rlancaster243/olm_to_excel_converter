"""Per-member context: settles every source value exactly once (W03/W04).

The core wraps the walker's stream (``values``), so the core, not the adapter,
counts source values. An adapter must settle each value it is given as mapped,
structural (via ``check_structural``), unknown (raw or lost) or lost. Values an
adapter leaves unsettled are swept to raw at the end of each record with an
ADAPTER_UNREPORTED warning, so an adapter cannot grade its own coverage.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator

from olm_excel.core.completeness import MemberAccount
from olm_excel.core.errors import ConversionError, ErrorCode
from olm_excel.core.raw_extract import MemberRawState, RawExtractor, XmlMember
from olm_excel.core.structural import DECLARATIONS, StructuralDeclaration
from olm_excel.core.walker import SourceValue


class StructuralStats:
    """Per-declaration counts for the manifest."""

    def __init__(self) -> None:
        self.consumed: Counter[str] = Counter()
        self.failed: Counter[str] = Counter()


class WarningLog:
    """Aggregated warnings. Details never contain source values."""

    def __init__(self) -> None:
        self._counts: Counter[tuple[str, str, str]] = Counter()

    def add(self, member_path: str, code: ErrorCode, detail: str) -> None:
        self._counts[(member_path, code.value, detail)] += 1

    def rows(self) -> list[tuple[str, str, str, str]]:
        return [(m, c, d, str(n)) for (m, c, d), n in sorted(self._counts.items())]

    def totals_by_code(self) -> Counter[str]:
        totals: Counter[str] = Counter()
        for (_, code, _), n in self._counts.items():
            totals[code] += n
        return totals


class MemberContext:
    def __init__(
        self,
        *,
        member: XmlMember,
        account: MemberAccount,
        extractor: RawExtractor,
        allowed_structural: tuple[str, ...],
        stats: StructuralStats,
        warnings: WarningLog,
        archive_id: str,
        provenance=None,
    ) -> None:
        unknown = [n for n in allowed_structural if n not in DECLARATIONS]
        if unknown:
            raise ValueError(f"unknown structural declarations: {unknown}")
        self.member = member
        self.account = account
        self.archive_id = archive_id
        self._extractor = extractor
        self._raw_state: MemberRawState = extractor.begin_member(member)
        self._allowed: tuple[StructuralDeclaration, ...] = tuple(DECLARATIONS[n] for n in allowed_structural)
        self._stats = stats
        self._warnings = warnings
        self._provenance = provenance
        self._window: dict[int, SourceValue] = {}
        self._deferred: list[tuple[StructuralDeclaration, SourceValue]] = []
        self._root = ""
        self._current: int | None = None  # ordinal of the value the adapter is processing right now

    def record_key(self, record_ordinal: int) -> str:
        return f"{self.archive_id}/{self.member.ordinal}/{record_ordinal}"

    def warn(self, code: ErrorCode, detail: str) -> None:
        self._warnings.add(self.member.path, code, detail)

    def values(self, source: Iterator[SourceValue]) -> Iterator[SourceValue]:
        """Count and register every value the walker yields, then hand it to the adapter."""
        try:
            for value in source:
                self.account.source_values += 1
                if not self._root:
                    path = value.element_path
                    self._root = path[1 : path.index("[")] if path.startswith("/") and "[" in path else ""
                self._window[value.node_ordinal] = value
                self._current = value.node_ordinal
                yield value
        finally:
            self._current = None

    def _take(self, value: SourceValue) -> None:
        if self._window.pop(value.node_ordinal, None) is None:
            raise ConversionError(ErrorCode.INTERNAL_ERROR, "a source value was settled twice or never issued", scope="member")

    def _log(self, value: SourceValue, status: str, detail: str = "") -> None:
        if self._provenance is not None:
            self._provenance.log(
                member_ordinal=self.member.ordinal,
                member_path=self.member.path,
                element_path=value.element_path,
                attribute=value.attribute,
                occurrence=value.node_ordinal,
                status=status,
                detail=detail,
                value=value.value,
            )

    def mapped(self, value: SourceValue, column: str = "") -> None:
        self._take(value)
        self.account.mapped += 1
        self._log(value, "mapped", column)

    def lost(self, value: SourceValue, reason: ErrorCode) -> None:
        self._take(value)
        self.account.add_lost(reason)
        self._log(value, f"lost:{reason.value}", reason.value)

    def unknown(self, value: SourceValue, record_key: str = "") -> None:
        """Route a value the adapter does not map to raw (or lost when raw extract is off)."""
        self._take(value)
        self._extractor.route(self._raw_state, value, self.account, record_key)

    def check_structural(self, value: SourceValue) -> bool:
        """True if the value was consumed as a declared, valid structural value."""
        for decl in self._allowed:
            if not decl.matches(value, self._root):
                continue
            if decl.deferred:
                self._take(value)
                self._deferred.append((decl, value))
                return True
            if decl.check(value.value):
                self._take(value)
                self.account.structural += 1
                self._stats.consumed[decl.name] += 1
                self._log(value, "structural", decl.name)
                return True
            self._stats.failed[decl.name] += 1
            self.warn(ErrorCode.STRUCTURAL_MISMATCH, f"{decl.name} has an invalid value")
            return False
        return False

    def end_record(self, record_key: str = "") -> None:
        """Sweep values the adapter left unsettled in this record to raw.

        The value being processed right now is skipped: when an adapter flushes the
        previous record on seeing the first value of the next one, that value is
        not yet part of the finished record.
        """
        for ordinal in sorted(self._window):
            if ordinal == self._current:
                continue
            value = self._window.pop(ordinal)
            self.warn(ErrorCode.ADAPTER_UNREPORTED, "adapter left a value unsettled")
            self._extractor.route(self._raw_state, value, self.account, record_key)

    def finish(self, *, records_seen: int, error: ConversionError | None = None) -> None:
        """Evaluate deferred structural checks, sweep leftovers and write the raw index row."""
        if error is not None:
            self.account.mark_uncounted(error.code)
        for decl, value in self._deferred:
            if error is None and decl.check_count(value.value, records_seen):
                self.account.structural += 1
                self._stats.consumed[decl.name] += 1
                self._log(value, "structural", decl.name)
            else:
                self._stats.failed[decl.name] += 1
                self.warn(ErrorCode.STRUCTURAL_MISMATCH, f"{decl.name} does not equal the number of records parsed")
                self._extractor.route(self._raw_state, value, self.account)
        self._deferred.clear()
        self.end_record()
        self._extractor.end_member(self._raw_state, self.account, error.code if error else None)
