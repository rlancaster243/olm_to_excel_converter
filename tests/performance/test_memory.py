"""ADR-004 / N02: walker memory is bounded by depth, not member size."""

from __future__ import annotations

import tracemalloc
import zipfile
from pathlib import Path

from olm_excel.core.walker import count_source_values
from olm_excel.core.xlsx_verify import verify_workbook
from olm_excel.core.xlsx_writer import WorkbookWriter

PEAK_LIMIT_BYTES = 5 * 1024 * 1024  # measured ~0.3 MB on the 19.8 MB sample XML


def test_walker_peak_memory_is_small_on_the_sample(sample_olm: Path) -> None:
    with zipfile.ZipFile(sample_olm) as z, z.open(z.namelist()[0]) as member:
        tracemalloc.start()
        try:
            count_source_values(member)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    assert peak < PEAK_LIMIT_BYTES, f"peak {peak / 1e6:.1f} MB"


def test_workbook_verification_memory_does_not_grow_with_rows(tmp_path: Path) -> None:
    rows = 150_000  # about 12 MB of retained row elements if finished rows stay attached to <sheetData>
    with WorkbookWriter(tmp_path / "big.xlsx") as writer:
        table = writer.add_table("data", ("a", "b"))
        for i in range(rows):
            table.append((str(i), "x"))
    tracemalloc.start()
    try:
        verify_workbook(tmp_path / "big.xlsx", writer.sheet_rows)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert writer.sheet_rows["data"] == rows + 1
    assert peak < 2 * 1024 * 1024, f"peak {peak / 1e6:.1f} MB"
