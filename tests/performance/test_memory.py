"""ADR-004 / N02: walker memory is bounded by depth, not member size."""

from __future__ import annotations

import tracemalloc
import zipfile
from pathlib import Path

from olm_excel.core.walker import count_source_values

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
