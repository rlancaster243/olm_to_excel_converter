"""The audit's workbook reader reports what is actually stored in each cell."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import xlsxwriter

from olm_excel.core.xlsx_read import Cell, column_index, iter_rows, sheet_names
from olm_excel.core.xlsx_writer import write_sheet


def test_column_index() -> None:
    assert [column_index(r) for r in ("A1", "B7", "Z1", "AA1", "AB10")] == [0, 1, 25, 26, 27]


def test_reads_converter_output_inline_strings_exactly(tmp_path: Path) -> None:
    out = tmp_path / "w.xlsx"
    values = ["+442012345678", "  padded  ", "=SUM(A1:A9)", "Café 東京", ""]
    write_sheet(out, "s", ([v] for v in values))
    rows = list(iter_rows(out, "s"))
    assert [r.get(0) for r in rows[:4]] == [Cell("text", v) for v in values[:4]]  # the empty string writes no cell
    assert sheet_names(out) == ["s"]


def test_reads_shared_strings_numbers_formulas_booleans_and_quote_prefix(tmp_path: Path) -> None:
    out = tmp_path / "w.xlsx"
    wb = xlsxwriter.Workbook(str(out))  # normal mode: shared strings
    ws = wb.add_worksheet("data")
    prefixed = wb.add_format()
    prefixed.set_quote_prefix()
    ws.write_string(0, 0, "+44 20 1234", prefixed)
    ws.write_string(0, 1, "+44 20 1234")
    ws.write_number(0, 2, 7123456789)
    ws.write_formula(0, 3, "=1+1", None, 2)
    ws.write_boolean(0, 4, True)
    wb.close()
    (row,) = list(iter_rows(out, "data"))
    assert row[0] == Cell("text", "+44 20 1234", True)
    assert row[1] == Cell("text", "+44 20 1234", False)
    assert row[2] == Cell("number", "7123456789")
    assert row[3].kind == "formula"
    assert row[4].kind == "bool"


def test_reads_a_workbook_saved_by_openpyxl(tmp_path: Path) -> None:
    out = tmp_path / "o.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "People"
    ws["A1"], ws["B1"], ws["C1"] = "07123 456789", 7123456789, "=A1"
    wb.save(out)
    (row,) = list(iter_rows(out, "People"))
    assert (row[0].kind, row[0].text) == ("text", "07123 456789")
    assert (row[1].kind, row[1].text) == ("number", "7123456789")
    assert row[2].kind == "formula"


def test_memory_does_not_grow_with_rows(tmp_path: Path) -> None:
    import tracemalloc

    out = tmp_path / "big.xlsx"
    write_sheet(out, "s", ([str(i), "x"] for i in range(100_000)))
    tracemalloc.start()
    count = sum(1 for _ in iter_rows(out, "s"))
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert count == 100_000 and peak < 2 * 1024 * 1024
