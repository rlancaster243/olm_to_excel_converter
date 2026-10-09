"""Target for W04: cell policy (F06, T07).

Values must round-trip exactly AND no cell may be a formula. Checking the
read-back value alone is not enough: a reader returns "=..." text for a live
formula cell too, so the sheet XML is inspected for formula elements.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import openpyxl

from olm_excel.core.xlsx_writer import write_sheet

HOSTILE_VALUES = [
    '=HYPERLINK("http://example.com","click")',  # from sample.olm notes
    "=SUM(A1:A9)",
    "+44 20 1234 5678 ext. 123",  # valid phone that a prefix-escape would corrupt
    "@channel ping",
    "-adjust",
    "0712 345678",  # leading zero must stay text
    "12345678901234567890",  # long numeric ID must not become a float
    "  leading and trailing whitespace  ",
    "Emoji 🙂, 東京, مرحبا",
    "Café Müller & Söhne",
]


def test_values_roundtrip_exactly_with_no_formula_cells(tmp_path: Path) -> None:
    out = tmp_path / "policy.xlsx"
    write_sheet(out, "values", ([v] for v in HOSTILE_VALUES))

    sheet_xml = zipfile.ZipFile(out).read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert not re.search(r"<f[ >]", sheet_xml), "formula cell written"

    sheet = openpyxl.load_workbook(out, read_only=True).worksheets[0]
    assert [row[0] for row in sheet.iter_rows(values_only=True)] == HOSTILE_VALUES
