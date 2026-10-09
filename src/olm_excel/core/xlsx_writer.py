"""Streaming workbook writer (W04/W05).

Contract: docs/fidelity/04-CONTRACTS-AND-DATA.md, "XLSX delivery contract".
Every value is written as an explicit string cell; text is never altered.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path


def write_sheet(path: Path, sheet_name: str, rows: Iterable[Sequence[str]]) -> None:
    """Write rows of literal strings to a single-sheet workbook at ``path``."""
    raise NotImplementedError("W04: xlsx writer cell policy")
