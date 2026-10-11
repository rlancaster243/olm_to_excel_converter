"""Raw extract end to end on the no-adapter path (F13, F14, T17-T21, T25 manifest)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import openpyxl
import pytest

from olm_excel.core.completeness import Outcome
from olm_excel.core.errors import ErrorCode
from olm_excel.core.raw_extract import RAW_COLUMNS, XmlMember, write_raw_workbook
from olm_excel.core.walker import count_source_values
from tests.helpers import read_rows

CONTACTS_MEMBER = "Accounts/test@example.com/Address Book/Contacts.xml"
EXPECTED_SOURCE_VALUES = 241_487


def member(ordinal: int, path: str, xml: bytes) -> XmlMember:
    return XmlMember(ordinal, path, lambda: io.BytesIO(xml))


@pytest.fixture(scope="module")
def sample_xml() -> bytes:
    with zipfile.ZipFile(Path(__file__).resolve().parents[2] / "docs/samples/sample.olm") as z:
        return z.read(CONTACTS_MEMBER)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(b"<contactEmailAddress ", b"<emailAddress ", id="T17-renamed-element"),
        pytest.param(b"<contacts>", b'<contacts xmlns="urn:x-olm:v2">', id="T18-root-namespace"),
    ],
)
def test_schema_variants_keep_every_source_value(sample_xml: bytes, old: bytes, new: bytes) -> None:
    variant = sample_xml.replace(old, new)
    assert variant != sample_xml
    assert count_source_values(io.BytesIO(variant)) == EXPECTED_SOURCE_VALUES


def test_sample_raw_workbook_holds_every_value(sample_xml: bytes, tmp_path: Path) -> None:
    out = tmp_path / "sample.xlsx"
    outcome, (acct,) = write_raw_workbook([member(1, CONTACTS_MEMBER, sample_xml)], out, submission_id="sub-1")

    assert outcome is Outcome.UNSUPPORTED  # no adapter yet: never SUCCESS (T06/T17)
    assert (acct.source_values, acct.raw, acct.lost_total, acct.counted) == (EXPECTED_SOURCE_VALUES, EXPECTED_SOURCE_VALUES, 0, True)

    raw = read_rows(out, "raw_0001")
    assert raw[0] == RAW_COLUMNS
    keys = [r[0] for r in raw[1:]]
    assert len(set(keys)) == EXPECTED_SOURCE_VALUES  # chunks share a raw_key
    long_note = [r for r in raw[1:] if r[9] == "2"]
    assert len(long_note) == 1  # the 40,000-character note is the only 2-chunk value

    manifest = dict(read_rows(out, "_manifest")[1:10])
    assert manifest["outcome"] == "UNSUPPORTED" and manifest["notice"].startswith("NOT FULLY CONVERTED")
    assert manifest["raw"] == str(EXPECTED_SOURCE_VALUES)
    index = read_rows(out, "_raw_index")
    assert index[1][4] == "raw_0001" and index[1][8] == "true"


def test_limit_marks_cut_member_and_still_indexes_later_members(tmp_path: Path) -> None:  # T19
    members = [member(i, f"m{i}.xml", b"<r><a>1</a><a>2</a><a>3</a></r>") for i in (1, 2, 3)]
    outcome, accounts = write_raw_workbook(members, tmp_path / "t19.xlsx", submission_id="s", max_values=4)
    assert [(a.raw, a.lost[ErrorCode.RAW_EXTRACT_LIMIT]) for a in accounts] == [(3, 0), (1, 2), (0, 3)]
    assert all(a.reconciles() and a.counted for a in accounts)
    index = read_rows(tmp_path / "t19.xlsx", "_raw_index")[1:]
    assert [(r[1], r[6], r[8], r[9]) for r in index] == [
        ("m1.xml", "3", "true", ""),
        ("m2.xml", "1", "false", "RAW_EXTRACT_LIMIT"),
        ("m3.xml", "0", "false", "RAW_EXTRACT_LIMIT"),
    ]
    assert outcome is Outcome.UNSUPPORTED


def test_opt_out_counts_values_as_lost_and_keeps_the_outcome(tmp_path: Path) -> None:  # T20
    members = [member(1, "m.xml", b"<r><a x='1'>2</a></r>")]
    on, (acct_on,) = write_raw_workbook(members, tmp_path / "on.xlsx", submission_id="s")
    off, (acct_off,) = write_raw_workbook(members, tmp_path / "off.xlsx", submission_id="s", raw_extract=False)
    assert on is off
    assert acct_on.raw == 2 and acct_off.raw == 0
    assert acct_off.lost == {ErrorCode.RAW_EXTRACT_DISABLED: 2}
    assert openpyxl.load_workbook(tmp_path / "off.xlsx", read_only=True).sheetnames == ["_manifest"]
    assert dict(read_rows(tmp_path / "off.xlsx", "_manifest")[1:])["raw_extract"] == "off"


def test_malformed_member_keeps_earlier_rows_and_is_uncounted(tmp_path: Path) -> None:  # T21
    members = [member(1, "bad.xml", b"<r><a>1</a><b>2</b><c>3</d></r>"), member(2, "ok.xml", b"<r>v</r>")]
    outcome, (bad, ok) = write_raw_workbook(members, tmp_path / "t21.xlsx", submission_id="s")
    assert bad.raw >= 2 and not bad.counted and bad.stop_reason is ErrorCode.RECORD_PARSE_ERROR
    assert ok.counted and ok.raw == 1
    index = read_rows(tmp_path / "t21.xlsx", "_raw_index")[1:]
    assert index[0][5].startswith("uncounted") and index[0][9] == "RECORD_PARSE_ERROR"
    assert outcome is Outcome.UNSUPPORTED


def test_quiet_unclaimed_member_still_gets_index_row(tmp_path: Path) -> None:  # finding #14, RE-053-18
    """An unclaimed member capped to 0 raw rows must still appear in _raw_index (raw=0, lost>0)."""
    members = [member(1, "capped.xml", b"<r><a>1</a></r>")]
    out = tmp_path / "quiet.xlsx"
    outcome, accounts = write_raw_workbook(members, out, submission_id="s", max_values=0)
    assert accounts[0].raw == 0 and accounts[0].lost_total > 0
    index = read_rows(out, "_raw_index")
    assert len(index) == 2  # header + one row
    assert index[1][1] == "capped.xml" and index[1][6] == "0" and index[1][8] == "false"
