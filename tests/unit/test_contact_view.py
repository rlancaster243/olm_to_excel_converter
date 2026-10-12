"""Contact list view (04, Contact list view): readable copy of settled values, never counted."""

from __future__ import annotations

from olm_excel.adapters.contact_view import (
    TRUNCATED,
    VIEW_HEADER,
    address,
    display_name,
    fit_cell,
    split_emails,
    view_row,
)
from olm_excel.core.xlsx_writer import utf16_len

P = "OPFContactCopy"


def email(address: str, default: str = "", kind: str = "work") -> dict[str, str]:
    return {
        "OPFContactEmailAddressAddress": address,
        "OPFContactEmailAddressIsDefault": default,
        "OPFContactEmailAddressType": kind,
    }


def row(**overrides) -> dict[str, str]:
    base = dict(record_key="k/1/1", scalars={}, emails=[], categories=[], primary_category="", children=[], picture_file="")
    base.update(overrides)
    return dict(zip(VIEW_HEADER, view_row(**base)))


def test_default_email_first_repeats_once_im_kept_apart() -> None:
    emails = [
        (f"{P}EmailAddressList", email("b@x.test")),
        (f"{P}EmailAddressList", email("a@x.test", default="1")),
        (f"{P}DefaultEmailAddress", email("A@X.test ", default="1")),  # same address as above, other case
        (f"{P}IMAddressList", email("im@x.test")),
    ]
    mail, im = split_emails(emails)
    assert mail == ["a@x.test", "b@x.test"]
    assert im == ["im@x.test"]


def test_more_than_three_emails_spill_to_more_emails() -> None:
    emails = [(f"{P}EmailAddressList", email(f"{n}@x.test")) for n in range(5)]
    r = row(emails=emails)
    assert [r["Email 1"], r["Email 2"], r["Email 3"]] == ["0@x.test", "1@x.test", "2@x.test"]
    assert r["More emails"] == "3@x.test; 4@x.test"


def test_address_is_one_line_and_skips_missing_parts() -> None:
    s = {f"{P}HomeStreetAddress": "1 Main St\r\nApt 2", f"{P}HomeCity": "Springfield", f"{P}HomeState": "IL",
         f"{P}HomeZip": "62701", f"{P}HomeCountry": "USA", f"{P}BusinessCity": "Tulsa"}
    assert address(s, "Home") == "1 Main St, Apt 2, Springfield, IL 62701, USA"
    assert address(s, "Business") == "Tulsa"
    assert address(s, "Other") == ""


def test_name_prefers_display_name_then_parts() -> None:
    assert display_name({f"{P}DisplayName": "Dr. Ann Lee", f"{P}FirstName": "Ann"}) == "Dr. Ann Lee"
    assert display_name({f"{P}FirstName": "Ann", f"{P}MiddleName": "B", f"{P}LastName": "Lee", f"{P}SetNameSuffix": "Jr."}) == "Ann B Lee Jr."
    assert display_name({}) == ""


def test_values_are_exact_text_dates_not_parsed_formulas_inert() -> None:
    r = row(scalars={f"{P}Birthday": "1990-02-03T00:00:00", f"{P}CellPhone": "+1 (555) 010", f"{P}BusinessCompany": "=SUM(A1)",
                     "OPFContactMainPhone": "0123"})
    assert r["Birthday"] == "1990-02-03T00:00:00"
    assert r["Mobile"] == "+1 (555) 010"
    assert r["Company"] == "=SUM(A1)"
    assert r["Main phone"] == "0123"


def test_notes_prefer_plain_text() -> None:
    assert row(scalars={f"{P}Notes": "<b>x</b>", f"{P}NotesPlain": "x"})["Notes"] == "x"
    assert row(scalars={f"{P}Notes": "<b>x</b>"})["Notes"] == "<b>x</b>"


def test_categories_primary_first_without_repeats_and_children_and_picture() -> None:
    r = row(categories=["Family", "Work"], primary_category="Work", children=["Sam", "Kim"],
            picture_file="out/pictures/ab12.png")
    assert r["Categories"] == "Work; Family"
    assert r["Children"] == "Sam; Kim"
    assert r["Picture"] == "ab12.png"
    assert r["Source ref"] == "k/1/1"


def test_system_fields_are_not_shown() -> None:
    for hidden in ("CanEdit", "CanDelete", "ExchangeID", "GetFlagStatus", "IsJapaneseContact", "FuriganaFirstName", "ModDate", "ContactImage"):
        assert hidden not in VIEW_HEADER


def test_over_cap_cell_is_cut_with_marker() -> None:
    long = "🙂" * 20_000  # 40,000 UTF-16 units
    cut = fit_cell(long)
    assert cut.endswith(TRUNCATED)
    assert utf16_len(cut) <= 32_767
    assert fit_cell("short") == "short"
