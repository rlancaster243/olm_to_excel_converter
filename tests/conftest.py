from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_OLM = REPO_ROOT / "docs" / "samples" / "sample.olm"  # synthetic, not a real export


@pytest.fixture
def sample_olm() -> Path:
    assert SAMPLE_OLM.is_file(), f"missing fixture {SAMPLE_OLM}"
    return SAMPLE_OLM
