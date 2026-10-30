"""Phone fidelity audit: counts only, per-key comparison of archive and workbook (T35)."""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

import openpyxl
import pytest

from olm_excel.core.convert import ConvertOptions, convert_archive
from olm_excel.core.phone_audit import PHONE_COLUMNS, audit_phones, numeric_inference_cause, shape_flags
from olm_excel.interfaces import cli
from tests.real_layout import SP, write_zip

PHONES = [
    "+44 20 1234 5678",      # 0
    "+442012345678",         # 1  numeric inference drops the plus
    "07123 456789",          # 2
    "07123456789",           # 3  numeric inference drops the leading zero
    "(555) 123-4567",        # 4
    "555-1234",              # 5
    "12345678901234567890",  # 6  more than 15 digits
    "555 0100 ext. 12",      # 7
    "  555 0100  ",          # 8  outer whitespace
    "1-2",                   # 9  date-like
    "5551234",               # 10 plain digits: safe as a number
    "=SUM(A1:A9)",           # 11
    "call mum",              # 12
    "-5551234",              # 13
]
FIELDS = ["OPFContactCopyCellPhone", "OPFContactCopyBusinessPhone", "OPFContactCopyHomePhone"]


def phone_archive(tmp_path: Path, name: str = "Outlook for Mac Archive.olm copy") -> Path:
    contacts = []
    for i, phone in enumerate(PHONES):
        contacts.append(
            f'<contact{SP}><OPFContactCopyDisplayName{SP}>Person {i}</OPFContactCopyDisplayName>'
            f'<{FIELDS[i % 3]}{SP}>{escape(phone)}</{FIELDS[i % 3]}></contact>'
        )
    xml = f'<?xml version="1.0"?><contacts{SP} elementCount="{len(PHONES)}">{"".join(contacts)}</contacts>'
    return write_zip(tmp_path / name, {"Accounts/a/Contacts/Contacts.xml": xml.encode()})


@pytest.fixture
def converted(tmp_path: Path):
    archive = phone_archive(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    result = convert_archive(archive, out, "result", ConvertOptions())
    assert result.error is None
    return archive, out / "result.xlsx"


def strings_in(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(map(str, obj)) | set().union(*(strings_in(v) for v in obj.values()))
    if isinstance(obj, list):
        return set().union(*(strings_in(v) for v in obj)) if obj else set()
    return {obj} if isinstance(obj, str) else set()


def test_source_shapes_are_counted_exactly(tmp_path: Path) -> None:
    report = audit_phones(phone_archive(tmp_path))
    src = report["source"]
    assert (src["contacts_members"], src["records"], src["phone_values"]) == (1, 14, 14)
    assert src["by_field"] == {"BusinessPhone": 5, "CellPhone": 5, "HomePhone": 4}
    assert src["shape_counts"] == {
        "plus_prefix": 2, "formula_prefix": 4, "digits_only": 3, "leading_zero": 2, "over_15_digits": 1,
        "has_separators": 10, "has_extension": 1, "has_letters": 2, "outer_whitespace": 1,
    }
    assert src["numeric_inference"] == {
        "would_alter": 4, "would_alter_pct": 28.57,
        "by_cause": {"date_like": 1, "leading_plus": 1, "leading_zero": 1, "over_15_digits": 1},
    }
    # Phones 0, 3, 6, 9, 12 go to CellPhone; 1, 4, 7, 10, 13 to BusinessPhone; 2, 5, 8, 11 to HomePhone.
    assert src["risk_by_field"] == {
        "BusinessPhone": {"values": 5, "would_alter": 1, "would_alter_pct": 20.0, "formula_prefix": 2, "formula_prefix_pct": 40.0},
        "CellPhone": {"values": 5, "would_alter": 3, "would_alter_pct": 60.0, "formula_prefix": 1, "formula_prefix_pct": 20.0},
        "HomePhone": {"values": 4, "would_alter": 0, "would_alter_pct": 0.0, "formula_prefix": 1, "formula_prefix_pct": 25.0},
    }
    assert "workbook" not in report


def test_the_converters_own_workbook_is_exact_for_every_phone_value(converted) -> None:
    archive, workbook = converted
    report = audit_phones(archive, workbook)
    for sheet in ("contacts", "contact_list"):
        part = report["workbook"][sheet]
        assert part["cells"] == {"exact": 14}, sheet
        assert part["exact_pct_of_source_phone_values"] == 100.0
        assert part["records_found"] == 14 and part["source_records_not_found"] == 0
    # Exact text, but no quote prefix: editing such a cell in Excel would re-parse it (the formula-prefix ones are at risk).
    assert report["workbook"]["contacts"]["quote_prefix"] == {
        "text_without_quote_prefix": 14, "formula_prefix_text_without_quote_prefix": 4,
    }


def test_a_garbled_workbook_is_detected_by_kind_and_cause(converted, tmp_path: Path) -> None:
    archive, workbook = converted
    wb = openpyxl.load_workbook(workbook)
    ws = wb["contacts"]
    header = [c.value for c in ws[1]]
    phone_cols = [header.index(c) for c in PHONE_COLUMNS if c in header]
    edits = {
        "07123456789": 7123456789,          # leading zero lost
        "+442012345678": 442012345678,      # plus lost
        "12345678901234567890": 1.2345678901234567e19,
        "5551234": 5551234,                  # same digits, wrong type
        "  555 0100  ": "555 0100",         # trimmed
        "555 0100 ext. 12": "555 0100",     # truncated
        "07123 456789": "07123 456780",     # different
        "call mum": None,                    # cell gone
        "=SUM(A1:A9)": "=SUM(A1:A9)",        # becomes a live formula (openpyxl treats a leading = as a formula)
    }
    for row in ws.iter_rows(min_row=2):
        for idx in phone_cols:
            cell = row[idx]
            if cell.value in edits:
                cell.value = edits[cell.value]
    garbled = tmp_path / "garbled.xlsx"
    wb.save(garbled)

    part = audit_phones(archive, garbled)["workbook"]["contacts"]
    assert part["cells"] == {
        "exact": 5, "number_altered": 3, "number_same_digits": 1, "whitespace_only": 1,
        "truncated": 1, "different": 1, "missing_cell": 1, "formula": 1,
    }
    assert part["number_cells_altered_by_cause"] == {"leading_plus": 1, "leading_zero": 1, "over_15_digits": 1}
    assert part["not_exact_by_source_shape"]["leading_zero"] == 2  # 07123456789 (number) and 07123 456789 (different)
    # The Contact list view was not edited, so it is still exact: each sheet is judged on its own.
    assert audit_phones(archive, garbled)["workbook"]["contact_list"]["cells"] == {"exact": 14}


def test_a_workbook_from_another_archive_is_reported_not_trusted(converted, tmp_path: Path) -> None:
    _, workbook = converted
    other = write_zip(
        tmp_path / "other.olm",
        {"Accounts/b/Contacts/Contacts.xml": f'<contacts{SP} elementCount="1"><contact{SP}><OPFContactCopyCellPhone{SP}>0123 4567</OPFContactCopyCellPhone></contact></contacts>'.encode()},
    )
    part = audit_phones(other, workbook)["workbook"]["contacts"]
    assert part["source_records_not_found"] == 1
    assert part["cells"] == {"missing_row": 1, "extra_cell_without_source": 14}  # every workbook phone cell has no source here


def test_the_report_contains_no_phone_values_or_names(converted) -> None:
    archive, workbook = converted
    report = audit_phones(archive, workbook)
    leaked = strings_in(report) & {*PHONES, *(f"Person {i}" for i in range(14)), "Outlook for Mac Archive.olm copy"}
    assert not leaked
    assert report["contains_values"] is False


def test_cli_exit_codes_and_summary(converted, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    archive, workbook = converted
    out = tmp_path / "report.json"
    assert cli.main(["audit-phones", str(archive), "--workbook", str(workbook), "-o", str(out)]) == 0
    text = capsys.readouterr().out
    assert "exact 14 (100.0%)" in text and "numeric inference would alter 4" in text
    assert not any(p in text for p in PHONES if len(p) > 6) and json.loads(out.read_text())["contains_values"] is False

    wb = openpyxl.load_workbook(workbook)
    ws = wb["contacts"]
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if cell.value == "07123456789":
                cell.value = 7123456789
    bad = tmp_path / "bad.xlsx"
    wb.save(bad)
    assert cli.main(["audit-phones", str(archive), "--workbook", str(bad), "-o", str(out)]) == 5
    assert "number_altered 1" in capsys.readouterr().out
    assert cli.main(["audit-phones", str(tmp_path / "missing.olm"), "-o", str(out)]) == 1


@pytest.mark.parametrize(
    ("text", "cause"),
    [
        ("+442012345678", "leading_plus"), ("07123456789", "leading_zero"), ("00123", "leading_zero"), ("-0123", "leading_zero"),
        ("1.5E+10", "exponent_form"), ("1234567890123456", "over_15_digits"), ("12/31", "date_like"), ("1-2", "date_like"),
        ("123456789012345", None), ("13/45", None), ("555-1234", None), ("(555) 123-4567", None), ("+1 555 123 4567", None),
        ("5551234", None), ("0", None), ("", None), ("  ", None), ("-5551234", None), ("0044 20 1234 5678", None),
    ],
)
def test_numeric_inference_model(text: str, cause: str | None) -> None:
    assert numeric_inference_cause(text) == cause


def test_shape_flags_never_echo_the_value() -> None:
    assert shape_flags("+44 20 1234") == ["plus_prefix", "formula_prefix", "has_separators"]
    assert shape_flags("   ") == ["empty_or_blank"]
    assert shape_flags("Zoë 555") == ["has_separators", "has_letters", "non_ascii"]
