"""Target for W04: the core walker's source-value count on the synthetic sample.

Oracle: 241,487 source values (77,592 attribute, 163,895 text, 0 empty),
counted independently on 2026-10-09 under the 04 "Source values" definition
(docs/fidelity/07-VERIFICATION-PLAN.md, T17/T18 oracle). Recount if the
fixture or the definition changes.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from olm_excel.core.raw_extract import count_source_values

CONTACTS_MEMBER = "Accounts/test@example.com/Address Book/Contacts.xml"  # synthetic layout guess
EXPECTED_SOURCE_VALUES = 241_487


def test_walker_counts_every_source_value(sample_olm: Path) -> None:
    with zipfile.ZipFile(sample_olm) as archive, archive.open(CONTACTS_MEMBER) as member:
        assert count_source_values(member) == EXPECTED_SOURCE_VALUES
