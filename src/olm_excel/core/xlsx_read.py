"""Minimal read-only XLSX reader (standard library plus defusedxml) for audits.

Unlike a spreadsheet library it reports what is actually stored in each cell: its kind (text, number,
formula, boolean, error), its raw text, and whether its style carries Excel's quote prefix. That is what
the phone audit needs: a number stored where text was expected is exactly the failure it looks for.

Streams each sheet and detaches finished rows, so memory does not grow with the row count. Shared strings
are loaded into memory (they are the workbook's own text, so this is bounded by the file).
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import defusedxml.ElementTree as SafeET

from olm_excel.core.xlsx_verify import sheet_parts

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REF = re.compile(r"([A-Z]+)")


@dataclass(frozen=True, slots=True)
class Cell:
    kind: str  # text | number | formula | bool | error | empty
    text: str  # raw stored text (for numbers, the digits as stored)
    quote_prefix: bool = False


def column_index(ref: str) -> int:
    """'B3' -> 1 (zero-based column)."""
    letters = _REF.match(ref).group(1)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        fh = archive.open("xl/sharedStrings.xml")
    except KeyError:
        return []
    strings: list[str] = []
    parts: list[str] = []
    in_phonetic = False
    with fh:
        for event, el in SafeET.iterparse(fh, events=("start", "end")):
            if event == "start":
                if el.tag == f"{_MAIN}rPh":
                    in_phonetic = True
                continue
            if el.tag == f"{_MAIN}rPh":
                in_phonetic = False
            elif el.tag == f"{_MAIN}t" and not in_phonetic:
                parts.append(el.text or "")
            elif el.tag == f"{_MAIN}si":
                strings.append("".join(parts))
                parts = []
                el.clear()
    return strings


def _quote_prefix_styles(archive: zipfile.ZipFile) -> list[bool]:
    """quotePrefix flag per cell format index (`s` attribute of a cell)."""
    try:
        fh = archive.open("xl/styles.xml")
    except KeyError:
        return []
    flags: list[bool] = []
    in_cell_xfs = False
    with fh:
        for event, el in SafeET.iterparse(fh, events=("start", "end")):
            if event == "start":
                if el.tag == f"{_MAIN}cellXfs":
                    in_cell_xfs = True
                continue
            if el.tag == f"{_MAIN}cellXfs":
                in_cell_xfs = False
            elif in_cell_xfs and el.tag == f"{_MAIN}xf":
                flags.append(el.get("quotePrefix") in ("1", "true"))
    return flags


def sheet_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return list(sheet_parts(archive))


def iter_rows(path: Path, sheet: str) -> Iterator[dict[int, Cell]]:
    """Yield each row of ``sheet`` as {zero-based column: Cell}. Empty cells are omitted."""
    with zipfile.ZipFile(path) as archive:
        part = sheet_parts(archive)[sheet]
        shared = _shared_strings(archive)
        quote = _quote_prefix_styles(archive)
        sheet_data = None
        row: dict[int, Cell] = {}
        attrs: dict[str, str] = {}
        value: str | None = None
        runs: list[str] = []
        has_formula = False
        with archive.open(part) as fh:
            for event, el in SafeET.iterparse(fh, events=("start", "end")):
                tag = el.tag
                if event == "start":
                    if tag == f"{_MAIN}sheetData":
                        sheet_data = el
                    elif tag == f"{_MAIN}row":
                        row = {}
                    elif tag == f"{_MAIN}c":
                        attrs, value, runs, has_formula = dict(el.attrib), None, [], False
                    continue
                if tag == f"{_MAIN}v":
                    value = el.text or ""
                elif tag == f"{_MAIN}t":
                    runs.append(el.text or "")
                elif tag == f"{_MAIN}f":
                    has_formula = True
                elif tag == f"{_MAIN}c":
                    kind, text = _classify(attrs.get("t"), value, runs, has_formula, shared)
                    if kind != "empty":
                        style = attrs.get("s")
                        flagged = bool(style and style.isdigit() and int(style) < len(quote) and quote[int(style)])
                        row[column_index(attrs["r"])] = Cell(kind, text, flagged)
                elif tag == f"{_MAIN}row":
                    yield row
                    el.clear()
                    if sheet_data is not None:
                        sheet_data.remove(el)


def _classify(t: str | None, value: str | None, runs: list[str], has_formula: bool, shared: list[str]) -> tuple[str, str]:
    if has_formula:
        return "formula", value or ""
    if t == "s":
        return "text", shared[int(value)] if value is not None and value.isdigit() and int(value) < len(shared) else ""
    if t == "inlineStr":
        return "text", "".join(runs)
    if t == "str":
        return "text", value or ""
    if t == "b":
        return "bool", value or ""
    if t == "e":
        return "error", value or ""
    if value is None:
        return "empty", ""
    return "number", value
