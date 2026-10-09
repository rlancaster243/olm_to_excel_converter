"""Writer contract: chunking, Excel limits, sheet names, atomic publication (T08, T12, T23)."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from olm_excel.core.errors import ConversionError, ErrorCode
from olm_excel.core.xlsx_writer import CHUNK_UTF16, WorkbookWriter, chunk_utf16, utf16_len, write_sheet
from tests.helpers import read_rows


def no_formulas(path: Path) -> bool:
    with zipfile.ZipFile(path) as z:
        return not any(
            re.search(r"<f[ >]", z.read(n).decode()) for n in z.namelist() if n.startswith("xl/worksheets/")
        )


class TestChunking:
    def test_short_text_is_one_chunk(self) -> None:
        assert chunk_utf16("abc") == ["abc"]
        assert chunk_utf16("") == [""]

    def test_long_text_splits_within_limit_and_rejoins_exactly(self) -> None:
        text = ("Long note filler sentence for cell-limit testing. " * 800)[:40000]  # as in sample.olm
        chunks = chunk_utf16(text)
        assert len(chunks) == 2
        assert all(utf16_len(c) <= CHUNK_UTF16 for c in chunks)
        assert "".join(chunks) == text

    def test_astral_characters_count_as_two_units_and_are_never_split(self) -> None:
        text = "🙂" * 20_000  # 40,000 UTF-16 units, 20,000 code points
        chunks = chunk_utf16(text)
        assert [utf16_len(c) for c in chunks] == [32_000, 8_000]
        assert "".join(chunks) == text

    def test_boundary_with_astral_character_falls_back_one_code_point(self) -> None:
        text = "a" * 31_999 + "🙂" + "b"
        chunks = chunk_utf16(text)
        assert chunks == ["a" * 31_999, "🙂b"]


class TestCellPolicy:
    def test_chunk_starting_with_equals_stays_text(self, tmp_path: Path) -> None:
        text = "x" * CHUNK_UTF16 + '=HYPERLINK("http://example.com","click")'
        out = tmp_path / "t23.xlsx"
        write_sheet(out, "s", ([c] for c in chunk_utf16(text)))
        assert no_formulas(out)
        assert "".join(r[0] for r in read_rows(out)) == text

    def test_ooxml_escapes_and_control_characters_roundtrip(self, tmp_path: Path) -> None:
        values = ["_x0041_ literal escape-like text", "ctl\x01char", "tab\tand\nnewline"]
        out = tmp_path / "escapes.xlsx"
        write_sheet(out, "s", ([v] for v in values))
        assert [r[0] for r in read_rows(out)] == values

    def test_oversize_cell_is_refused_not_truncated(self, tmp_path: Path) -> None:
        with pytest.raises(ConversionError) as exc:
            write_sheet(tmp_path / "big.xlsx", "s", [["a" * 32_768]])
        assert exc.value.code is ErrorCode.EXCEL_LIMIT
        assert not (tmp_path / "big.xlsx").exists()

    def test_astral_oversize_is_measured_in_utf16_units(self, tmp_path: Path) -> None:
        with pytest.raises(ConversionError):
            write_sheet(tmp_path / "big.xlsx", "s", [["🙂" * 16_384]])  # 16,384 code points, 32,768 units

    def test_non_string_values_are_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            write_sheet(tmp_path / "n.xlsx", "s", [[42]])  # type: ignore[list-item]


class TestPartitioning:
    def test_partitioned_table_spills_into_numbered_sheets_with_header(self, tmp_path: Path) -> None:
        out = tmp_path / "p.xlsx"
        with WorkbookWriter(out, max_rows=3) as w:
            t = w.add_table("raw", ("h",), partitioned=True)
            for i in range(5):
                t.append((str(i),))
        assert t.partition_names == ["raw_0001", "raw_0002", "raw_0003"]
        assert read_rows(out, "raw_0001") == [("h",), ("0",), ("1",)]
        assert read_rows(out, "raw_0003") == [("h",), ("4",)]

    def test_unpartitioned_overflow_is_an_excel_limit(self, tmp_path: Path) -> None:
        with pytest.raises(ConversionError) as exc:
            with WorkbookWriter(tmp_path / "o.xlsx", max_rows=2) as w:
                t = w.add_table("s")
                for i in range(3):
                    t.append((str(i),))
        assert exc.value.code is ErrorCode.EXCEL_LIMIT


class TestSheetNames:
    @pytest.mark.parametrize("name", ["", "x" * 32, "a/b", "a[1]", "q?", "'quoted"])
    def test_invalid_names_rejected(self, tmp_path: Path, name: str) -> None:
        with pytest.raises(ConversionError):
            with WorkbookWriter(tmp_path / "n.xlsx") as w:
                w.add_table(name)

    def test_duplicate_names_rejected_case_insensitively(self, tmp_path: Path) -> None:
        with pytest.raises(ConversionError):
            with WorkbookWriter(tmp_path / "d.xlsx") as w:
                w.add_table("Raw")
                w.add_table("raw")


class TestAtomicPublication:
    def test_clean_close_publishes_and_leaves_no_partial(self, tmp_path: Path) -> None:
        out = tmp_path / "ok.xlsx"
        write_sheet(out, "s", [["v"]])
        assert out.exists() and not (tmp_path / "ok.xlsx.partial").exists()

    def test_failure_mid_write_publishes_nothing(self, tmp_path: Path) -> None:
        out = tmp_path / "fail.xlsx"
        with pytest.raises(RuntimeError):
            with WorkbookWriter(out) as w:
                w.add_table("s").append(("v",))
                raise RuntimeError("simulated crash")
        assert list(tmp_path.iterdir()) == []
