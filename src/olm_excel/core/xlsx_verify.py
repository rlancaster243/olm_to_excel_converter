"""Post-write workbook verification (03 end-to-end step 6).

Re-reads a closed workbook with the standard library only and checks that:
- the sheet names are exactly the expected ones;
- each sheet holds exactly the expected number of rows;
- no cell is a formula.

It streams each sheet, so it uses bounded memory on large workbooks.
"""

from __future__ import annotations

import posixpath
import zipfile
from collections.abc import Mapping
from pathlib import Path

import defusedxml.ElementTree as SafeET

from olm_excel.core.errors import ConversionError, ErrorCode

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _fail(message: str) -> ConversionError:
    return ConversionError(ErrorCode.OUTPUT_IO, f"workbook verification failed: {message}", scope="workbook")


def sheet_parts(archive: zipfile.ZipFile) -> dict[str, str]:
    """Map sheet name to its part path inside the workbook package."""
    rels: dict[str, str] = {}
    with archive.open("xl/_rels/workbook.xml.rels") as fh:
        for _, el in SafeET.iterparse(fh):
            if el.tag == f"{_REL}Relationship":
                rels[el.get("Id")] = posixpath.normpath(posixpath.join("xl", el.get("Target")))
    parts: dict[str, str] = {}
    with archive.open("xl/workbook.xml") as fh:
        for _, el in SafeET.iterparse(fh):
            if el.tag == f"{_MAIN}sheet":
                parts[el.get("name")] = rels[el.get(f"{_DOC_REL}id")]
    return parts


def verify_workbook(path: Path, expected_rows: Mapping[str, int]) -> None:
    """Raise ``ConversionError(OUTPUT_IO)`` unless ``path`` matches ``expected_rows`` and has no formulas."""
    try:
        with zipfile.ZipFile(path) as archive:
            parts = sheet_parts(archive)
            if set(parts) != set(expected_rows):
                raise _fail("sheet names differ from the expected set")
            for name, part in parts.items():
                rows = 0
                sheet_data = None
                with archive.open(part) as fh:
                    for event, el in SafeET.iterparse(fh, events=("start", "end")):
                        if event == "start":
                            if el.tag == f"{_MAIN}sheetData":
                                sheet_data = el
                            continue
                        if el.tag == f"{_MAIN}f":
                            raise _fail(f"formula cell found in sheet {name!r}")
                        if el.tag == f"{_MAIN}row":
                            rows += 1
                            el.clear()
                            sheet_data.remove(el)  # clear() alone leaves an empty element per row attached
                if rows != expected_rows[name]:
                    raise _fail(f"sheet {name!r} has {rows} rows, expected {expected_rows[name]}")
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise _fail(type(exc).__name__) from exc
