"""Streaming workbook writer (W04).

Contract: docs/fidelity/04-CONTRACTS-AND-DATA.md, "XLSX delivery contract".
- Every value is written as an explicit string cell, so formula-like text
  stays inert and is never prefixed or altered (F06).
- XlsxWriter's constant_memory mode keeps memory flat (ADR-004).
- A cell over Excel's 32,767 UTF-16 unit cap is refused, never truncated;
  callers split long values with ``chunk_utf16`` first.
- The workbook is written to ``<name>.partial`` and renamed into place only
  on a clean close, so a crash never leaves a file that looks finished.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from types import TracebackType

import xlsxwriter

from olm_excel.core.errors import ConversionError, ErrorCode

EXCEL_MAX_ROWS = 1_048_576
EXCEL_CELL_MAX_UTF16 = 32_767
CHUNK_UTF16 = 32_000  # fixed headroom below the cell cap (04 chunking rule)
SHEET_NAME_MAX = 31
_SHEET_NAME_FORBIDDEN = set("[]:*?/\\")

_WORKBOOK_OPTIONS = {
    "constant_memory": True,
    "strings_to_formulas": False,
    "strings_to_numbers": False,
    "strings_to_urls": False,
}


def utf16_len(text: str) -> int:
    """Length in UTF-16 code units, which is what Excel's cell cap counts."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def chunk_utf16(text: str, max_units: int = CHUNK_UTF16) -> list[str]:
    """Split ``text`` into ordered chunks of at most ``max_units`` UTF-16 units.

    Python strings index by code point, so a split never lands inside a
    surrogate pair. Joining the chunks gives back ``text`` exactly.
    """
    if len(text) <= max_units // 2 or utf16_len(text) <= max_units:
        return [text]
    chunks: list[str] = []
    start = units = 0
    for i, ch in enumerate(text):
        width = 2 if ord(ch) > 0xFFFF else 1
        if units + width > max_units:
            chunks.append(text[start:i])
            start, units = i, 0
        units += width
    chunks.append(text[start:])
    return chunks


def _check_sheet_name(name: str) -> None:
    if not name or len(name) > SHEET_NAME_MAX or _SHEET_NAME_FORBIDDEN & set(name) or name.startswith("'"):
        raise ConversionError(ErrorCode.EXCEL_LIMIT, f"invalid sheet name {name!r}", scope="workbook")


class Table:
    """Rows appended to one sheet, or to numbered partitions of it."""

    def __init__(
        self,
        writer: WorkbookWriter,
        name: str,
        header: Sequence[str] | None,
        partitioned: bool,
        max_rows: int,
        spill: bool = False,
    ):
        self._writer = writer
        self._name = name
        self._header = tuple(header) if header else None
        self._partitioned = partitioned
        self._spill = spill  # first sheet keeps `name`; overflow goes to name_0002, name_0003, ...
        self._max_rows = max_rows
        self.partition_names: list[str] = []
        self._sheet = None
        self._row = 0
        self._new_sheet()

    @property
    def partition_count(self) -> int:
        return len(self.partition_names)

    def next_row_partition(self) -> int:
        """Index into ``partition_names`` of the sheet the next appended row lands in."""
        full = self._row >= self._max_rows
        return len(self.partition_names) if full and (self._partitioned or self._spill) else len(self.partition_names) - 1

    def _new_sheet(self) -> None:
        number = len(self.partition_names) + 1
        if self._partitioned or (self._spill and number > 1):
            name = f"{self._name}_{number:04d}"
        else:
            name = self._name
        self._sheet = self._writer._add_worksheet(name)
        self.partition_names.append(name)
        self._writer.sheet_rows[name] = 0
        self._row = 0
        if self._header:
            self._write(self._header)

    def append(self, row: Sequence[str]) -> None:
        if self._row >= self._max_rows:
            if not (self._partitioned or self._spill):
                raise ConversionError(ErrorCode.EXCEL_LIMIT, f"sheet {self._name} exceeds {self._max_rows} rows", scope="workbook")
            self._new_sheet()
        self._write(row)

    def _write(self, row: Sequence[str]) -> None:
        for col, value in enumerate(row):
            if not isinstance(value, str):
                raise TypeError(f"cell values must be str, got {type(value).__name__}")
            if len(value) > EXCEL_CELL_MAX_UTF16 // 2 and utf16_len(value) > EXCEL_CELL_MAX_UTF16:
                raise ConversionError(ErrorCode.EXCEL_LIMIT, "cell exceeds 32,767 UTF-16 units; chunk it first", scope="workbook")
            status = self._sheet.write_string(self._row, col, value)
            if status != 0:  # -2 would mean XlsxWriter truncated the value
                raise ConversionError(ErrorCode.EXCEL_LIMIT, f"write_string returned {status}", scope="workbook")
        self._row += 1
        self._writer.sheet_rows[self.partition_names[-1]] = self._row


class WorkbookWriter:
    """Context manager for one output workbook with atomic publication."""

    def __init__(self, target: Path, *, max_rows: int = EXCEL_MAX_ROWS) -> None:
        self.target = Path(target)
        self.partial = self.target.with_name(self.target.name + ".partial")
        self._max_rows = max_rows
        self._names: set[str] = set()
        self.sheet_rows: dict[str, int] = {}  # rows written per sheet, header included
        self._workbook = xlsxwriter.Workbook(str(self.partial), _WORKBOOK_OPTIONS)
        self._closed = False

    def add_table(
        self,
        name: str,
        header: Sequence[str] | None = None,
        *,
        partitioned: bool = False,
        spill: bool = False,
    ) -> Table:
        """Add a sheet. ``partitioned`` numbers every sheet (raw_0001); ``spill`` only numbers overflow."""
        return Table(self, name, header, partitioned, self._max_rows, spill)

    def _add_worksheet(self, name: str):
        _check_sheet_name(name)
        if name.lower() in self._names:  # Excel sheet names are case-insensitive
            raise ConversionError(ErrorCode.EXCEL_LIMIT, f"duplicate sheet name {name!r}", scope="workbook")
        self._names.add(name.lower())
        return self._workbook.add_worksheet(name)

    def publish(self, verify: Callable[[Path], None] | None = None) -> Path:
        """Close the workbook, optionally verify the closed file, then atomically move it to ``target``."""
        try:
            self._workbook.close()
        except Exception as exc:
            self.abort()
            raise ConversionError(ErrorCode.OUTPUT_IO, f"workbook close failed: {type(exc).__name__}", scope="workbook") from exc
        self._closed = True
        if verify is not None:
            try:
                verify(self.partial)
            except BaseException:
                self.partial.unlink(missing_ok=True)
                raise
        os.replace(self.partial, self.target)
        return self.target

    def abort(self) -> None:
        """Discard the partial workbook. Safe to call more than once."""
        if not self._closed:
            self._closed = True
            try:
                self._workbook.close()
            except Exception:
                pass
        self.partial.unlink(missing_ok=True)

    def __enter__(self) -> WorkbookWriter:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        if exc_type is not None:
            self.abort()
        elif not self._closed:
            self.publish()


def write_sheet(path: Path, sheet_name: str, rows: Iterable[Sequence[str]]) -> None:
    """Write rows of literal strings to a single-sheet workbook at ``path``."""
    with WorkbookWriter(path) as writer:
        table = writer.add_table(sheet_name)
        for row in rows:
            table.append(row)
