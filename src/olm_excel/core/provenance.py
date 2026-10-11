"""Provenance bijection for content checks (finding #7).

Key k = (member_ordinal, element_path, attribute, node_ordinal). node_ordinal
is document order within the member, so k is unique per source value and lets
an independent reader verify that every value was accounted for exactly once.

Only hashes are stored in the workbook, never values (N05). Sums are mod 2**64
so swap/drop/duplicate/truncate mutations change them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

PROVENANCE_HEADER = (
    "member_ordinal",
    "member_path",
    "element_path",
    "attribute",
    "occurrence",
    "status",
    "detail",
    "value_hash",
)
COLUMNS_HEADER = ("adapter_id", "sheet", "column", "source")
MASK64 = (1 << 64) - 1


def value_hash(text: str) -> str:
    """Hex hash of one value (blake2b-64, hex). Empty string hashes deterministically."""
    return hashlib.blake2b(text.encode("utf-8", "surrogatepass"), digest_size=8).hexdigest()


def hash_int(text: str) -> int:
    return int.from_bytes(
        hashlib.blake2b(text.encode("utf-8", "surrogatepass"), digest_size=8).digest(), "big"
    )


def sum_mod64(texts) -> int:
    """Order-sensitive rolling sum mod 2**64 (finding #8): swaps change it, not just drops."""
    total = 0
    for t in texts:
        total = ((total * 1315423911) + hash_int(t)) & MASK64
    return total


@dataclass
class ProvenanceRecord:
    member_ordinal: int
    member_path: str
    element_path: str
    attribute: str
    occurrence: int
    status: str
    detail: str
    value_hash: str


@dataclass
class ProvenanceLog:
    """Collects one record per settled source value. Written as _provenance for lost+structural only."""

    records: list[ProvenanceRecord] = field(default_factory=list)

    def log(
        self,
        *,
        member_ordinal: int,
        member_path: str,
        element_path: str,
        attribute: str,
        occurrence: int,
        status: str,
        detail: str,
        value: str,
    ) -> None:
        self.records.append(
            ProvenanceRecord(
                member_ordinal, member_path, element_path, attribute, occurrence,
                status, detail, value_hash(value),
            )
        )

    def keys(self) -> set[tuple]:
        return {
            (r.member_ordinal, r.element_path, r.attribute, r.occurrence) for r in self.records
        }

    def sums_by_status(self) -> dict[str, int]:
        # Order-sensitive rolling sums grouped by status prefix.
        out: dict[str, int] = {}
        for r in self.records:
            base = r.status.split(":")[0]
            out[base] = ((out.get(base, 0) * 1315423911 + int(r.value_hash, 16)) & MASK64)
        return out

    def ledger_rows(self) -> list[tuple[str, ...]]:
        """Rows for lost + structural only, keyed by k."""
        rows = []
        for r in self.records:
            if r.status.startswith("lost") or r.status.startswith("structural"):
                rows.append((
                    str(r.member_ordinal), r.member_path, r.element_path, r.attribute,
                    str(r.occurrence), r.status, r.detail, r.value_hash,
                ))
        return rows
