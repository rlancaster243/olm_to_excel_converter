"""Test-only oracles. Independent of the code under test by design (07)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import openpyxl

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_XSTRING_ESCAPE = re.compile(r"_x([0-9A-Fa-f]{4})_")


def decode_xstring(text: str | None) -> str | None:
    """Decode OOXML ST_Xstring escapes (`_xHHHH_`), as Excel does on open.

    openpyxl returns these escapes undecoded, so it is not a faithful
    reader for control characters or literal `_xHHHH_` text by itself.
    """
    if text is None:
        return None
    return _XSTRING_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), text)


def read_rows(path: Path, sheet: str | int = 0) -> list[tuple[str | None, ...]]:
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.worksheets[sheet] if isinstance(sheet, int) else wb[sheet]
    rows = [tuple(decode_xstring(v) for v in row) for row in ws.iter_rows(values_only=True)]
    wb.close()
    return rows


def reference_values(xml: bytes) -> list[tuple[str, str, str]]:
    """Whole-document (non-streaming) reference for the 04 Source values rules.

    Returns (value_kind, attribute, value) in document order.
    """
    out: list[tuple[str, str, str]] = []

    def text_ok(t: str | None, has_children: bool, preserve: bool) -> bool:
        return bool(t) and (bool(t.strip()) or not has_children or preserve)

    def walk(el: ET.Element, preserve: bool) -> None:
        space = el.get(XML_SPACE)
        preserve = True if space == "preserve" else False if space == "default" else preserve
        out.extend(("attribute", k, v) for k, v in el.attrib.items())
        kids = list(el)
        if text_ok(el.text, bool(kids), preserve):
            out.append(("text", "", el.text))
        for kid in kids:
            walk(kid, preserve)
            if text_ok(kid.tail, True, preserve):
                out.append(("text", "", kid.tail))
        if not el.attrib and not kids and not el.text:
            out.append(("empty", "", ""))

    walk(ET.fromstring(xml), False)
    return out


def sheet_names(path: Path) -> list[str]:
    wb = openpyxl.load_workbook(path, read_only=True)
    names = list(wb.sheetnames)
    wb.close()
    return names


def table_rows(path: Path, sheet: str) -> list[dict[str, str | None]]:
    """Rows of a sheet as dicts keyed by the header row."""
    rows = read_rows(path, sheet)
    header = rows[0]
    return [dict(zip(header, row)) for row in rows[1:]]
