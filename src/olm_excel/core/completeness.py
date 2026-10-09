"""Field-level completeness accounting and the outcome rule (W04).

Contract: docs/fidelity/04-CONTRACTS-AND-DATA.md, "Completeness contract".
Per XML member: source_values == mapped + structural + raw + lost. SUCCESS
requires raw == 0 and lost == 0 everywhere, so raw output never upgrades an
outcome and the raw extract flag never changes it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from olm_excel.core.errors import ConversionError, ErrorCode

LOSS_REASONS = frozenset({
    ErrorCode.RAW_EXTRACT_DISABLED,
    ErrorCode.RAW_EXTRACT_LIMIT,
    ErrorCode.RECORD_PARSE_ERROR,
    ErrorCode.EXCEL_LIMIT,
    ErrorCode.PICTURE_NOT_EXPORTED,
})


class Outcome(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class MemberAccount:
    member_path: str
    source_values: int = 0
    mapped: int = 0
    structural: int = 0
    raw: int = 0
    lost: Counter[ErrorCode] = field(default_factory=Counter)
    counted: bool = True  # False when the walk stopped before the member ended
    stop_reason: ErrorCode | None = None

    @property
    def lost_total(self) -> int:
        return sum(self.lost.values())

    def add_lost(self, reason: ErrorCode, n: int = 1) -> None:
        if reason not in LOSS_REASONS:
            raise ValueError(f"not a loss reason: {reason}")
        self.lost[reason] += n

    def mark_uncounted(self, reason: ErrorCode) -> None:
        self.counted = False
        self.stop_reason = reason

    def reconciles(self) -> bool:
        return self.source_values == self.mapped + self.structural + self.raw + self.lost_total

    @property
    def fully_mapped(self) -> bool:
        return self.counted and self.raw == 0 and self.lost_total == 0


def decide_outcome(
    accounts: Iterable[MemberAccount],
    *,
    families_converted: int,
    unclaimed_non_xml_members: int = 0,
) -> Outcome:
    """Apply the 04 outcome rule. FAILED and CANCELLED are decided by the caller.

    Raises INTERNAL_ERROR if any member's counters do not reconcile: that is
    a bug, never a reportable outcome.
    """
    accounts = list(accounts)
    broken = [a.member_path for a in accounts if not a.reconciles()]
    if broken:
        raise ConversionError(
            ErrorCode.INTERNAL_ERROR, f"{len(broken)} member(s) fail mapped + structural + raw + lost reconciliation",
            scope="archive",
        )
    if families_converted == 0:
        return Outcome.UNSUPPORTED
    if unclaimed_non_xml_members == 0 and all(a.fully_mapped for a in accounts):
        return Outcome.SUCCESS
    return Outcome.PARTIAL


@dataclass(frozen=True)
class Totals:
    source_values: int
    mapped: int
    structural: int
    raw: int
    lost: int
    uncounted_members: int


def totals(accounts: Iterable[MemberAccount]) -> Totals:
    accounts = list(accounts)
    return Totals(
        source_values=sum(a.source_values for a in accounts),
        mapped=sum(a.mapped for a in accounts),
        structural=sum(a.structural for a in accounts),
        raw=sum(a.raw for a in accounts),
        lost=sum(a.lost_total for a in accounts),
        uncounted_members=sum(not a.counted for a in accounts),
    )


def manifest_rows(outcome: Outcome, accounts: Iterable[MemberAccount], *, raw_extract: bool) -> list[tuple[str, str]]:
    """Leading `_manifest` rows: outcome and counts first, so a PARTIAL or
    UNSUPPORTED download never reads as a full conversion (02 decision)."""
    t = totals(accounts)
    notice = (
        "Fully converted."
        if outcome is Outcome.SUCCESS
        else "NOT FULLY CONVERTED. Raw and lost values are listed; check the counts below before relying on this file."
    )
    return [
        ("outcome", outcome.value),
        ("notice", notice),
        ("source_values", str(t.source_values)),
        ("mapped", str(t.mapped)),
        ("structural", str(t.structural)),
        ("raw", str(t.raw)),
        ("lost", str(t.lost)),
        ("uncounted_members", str(t.uncounted_members)),
        ("raw_extract", "on" if raw_extract else "off"),
    ]
