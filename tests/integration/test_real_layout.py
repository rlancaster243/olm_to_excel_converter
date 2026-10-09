"""Conversion of the real layout (E09), on synthetic archives with fake values (T26-T34, T24, F15, F16)."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import openpyxl
import pytest

from olm_excel.core.completeness import Outcome
from olm_excel.core.convert import ConvertOptions, convert_archive
from olm_excel.core.errors import ErrorCode
from tests.helpers import reference_values, sheet_names, table_rows
from tests.real_layout import LONG_NOTE, MEMBER_PATHS, PNG_1X1, SP, build_archive, categories_member, contacts_member, write_zip
from tests.real_layout import Expect

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def run(tmp_path: Path, archive: Path, **options):
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    return convert_archive(archive, out, "result", ConvertOptions(**options)), out / "result.xlsx"


def manifest(path: Path) -> dict[str, str]:
    return {r["key"]: r["value"] for r in table_rows(path, "_manifest")}


@pytest.fixture
def built(tmp_path: Path):
    archive = tmp_path / "Outlook for Mac Archive.olm copy"  # the real file name: the extension must not matter
    return archive, build_archive(archive)


def test_default_conversion_reconciles_and_is_partial_only_because_pictures_are_not_exported(tmp_path: Path, built) -> None:
    archive, exp = built
    result, wb = run(tmp_path, archive)
    assert result.error is None and result.outcome is Outcome.PARTIAL

    t = result.totals
    assert (t.raw, t.uncounted_members) == (0, 0)
    assert t.lost == exp.pictures and result.lost_by_reason == {"PICTURE_NOT_EXPORTED": exp.pictures}
    assert t.source_values == t.mapped + t.structural + t.raw + t.lost

    # Independent oracle: the DOM reference counts every source value and every structural attribute.
    reference = {p: reference_values(x) for p, x in exp.members_xml.items()}
    assert t.source_values == sum(len(v) for v in reference.values())
    structural = sum(1 for vals in reference.values() for kind, attr, _ in vals if attr == XML_SPACE or attr == "elementCount")
    assert t.structural == structural == exp.structural
    assert result.structural == {"elementCount": (4, 0), "xml:space": (structural - 4, 0)}

    for member in result.members:
        assert member.account.reconciles() and member.account.counted
        assert member.account.source_values == len(reference[member.path])

    assert len(table_rows(wb, "contacts")) == exp.total_contacts
    assert len(table_rows(wb, "contact_emails")) == exp.emails
    assert len(table_rows(wb, "contact_categories")) == exp.category_rows
    assert len(table_rows(wb, "contact_lists")) == exp.list_rows >= 1
    assert len(table_rows(wb, "contact_pictures")) == exp.pictures
    assert len(table_rows(wb, "categories")) == exp.global_categories
    assert "raw_0001" not in sheet_names(wb)  # clean conversion: no raw sheets

    m = manifest(wb)
    assert m["outcome"] == "PARTIAL"
    assert m["notice"] == (
        f"PARTIAL only because {exp.pictures} contact pictures were not exported. "
        "Re-run with image export (--export-images) to include them."
    )
    assert result.notice == m["notice"]
    assert (m["structural"], m["raw"], m["lost"]) == (str(structural), "0", str(exp.pictures))
    assert m["lost:PICTURE_NOT_EXPORTED"] == str(exp.pictures)
    assert m["adapter:contacts-olm-v1"] == "1.0.0" and m["adapter:categories-olm-v1"] == "1.0.0"
    assert m["structural:elementCount"] == "consumed=4 failed=0"


def test_export_images_makes_the_conversion_a_success_with_content_addressed_files(tmp_path: Path, built) -> None:
    archive, exp = built
    result, wb = run(tmp_path, archive, export_images=True)
    assert result.outcome is Outcome.SUCCESS and result.totals.lost == 0

    digest = hashlib.sha256(PNG_1X1).hexdigest()
    pictures_dir = tmp_path / "out" / "result-pictures"
    assert [p.name for p in pictures_dir.iterdir()] == [f"{digest[:16]}.png"]  # identical images share one file
    assert (pictures_dir / f"{digest[:16]}.png").read_bytes() == PNG_1X1
    rows = table_rows(wb, "contact_pictures")
    assert len(rows) == exp.pictures
    assert {(r["encoding"], r["detected_format"], r["hash_basis"], r["sha256"], r["decoded_bytes"], r["type_declared"]) for r in rows} == {
        ("base64", "png", "decoded_bytes", digest, str(len(PNG_1X1)), "image/png")
    }
    assert {r["exported_file"] for r in rows} == {f"result-pictures/{digest[:16]}.png"}
    assert result.pictures_written == 1 and not (tmp_path / "out" / "result-pictures.partial").exists()


def test_no_picture_text_reaches_any_cell(tmp_path: Path, built) -> None:
    archive, _ = built
    _, wb = run(tmp_path, archive)
    encoded = base64.b64encode(PNG_1X1).decode()
    book = openpyxl.load_workbook(wb, read_only=True)
    for sheet in book.worksheets:
        for row in sheet.iter_rows(values_only=True):
            assert not any(isinstance(v, str) and encoded in v for v in row), sheet.title


def test_values_are_exact_text_with_no_formulas_or_date_cells(tmp_path: Path, built) -> None:  # T32
    archive, _ = built
    _, wb = run(tmp_path, archive)
    rows = {r["ExchangeID"]: r for r in table_rows(wb, "contacts")}
    assert rows["EX00000004"]["BusinessPhone"] == "=SUM(A1:A9)"
    assert rows["EX00000002"]["BusinessPhone"] == "+44 20 1234 5678"
    assert rows["EX00000003"]["CellPhone"] == "0712 345678"
    assert rows["EX00000005"]["Birthday"] == "1975-03-12T00:00:00"
    assert rows["EX00000001"]["BusinessCompany"] == "Café Müller & Söhne 東京"
    assert rows["EX00000001"]["Notes"] == "<html>note 1 &amp; more</html>"
    book = openpyxl.load_workbook(wb, read_only=True)
    for sheet in book.worksheets:
        for row in sheet.iter_rows():
            assert all(c.data_type in ("s", "n") and (c.data_type == "s" or c.value is None) for c in row if c.value is not None), sheet.title


def test_long_note_is_split_exactly(tmp_path: Path, built) -> None:
    archive, exp = built
    result, wb = run(tmp_path, archive)
    contacts = {r["contact_ordinal"]: r for r in table_rows(wb, "contacts") if r["source_member"] == MEMBER_PATHS["main"]}
    first = contacts["2"]["NotesPlain"]
    chunks = {int(r["chunk"]): r["value"] for r in table_rows(wb, "contact_long_text") if r["field"] == "NotesPlain"}
    assert len(first.encode("utf-16-le")) // 2 <= 32_000 and set(chunks) == {2}
    assert first + chunks[2] == LONG_NOTE
    assert len(table_rows(wb, "contact_long_text")) == exp.long_text_values


def test_email_containers_keep_every_element_without_deduplication(tmp_path: Path, built) -> None:  # T30
    archive, exp = built
    _, wb = run(tmp_path, archive)
    rows = table_rows(wb, "contact_emails")
    assert len(rows) == exp.emails
    assert {r["list_source"] for r in rows} <= {"OPFContactCopyEmailAddressList", "OPFContactCopyEmailAddressList1", "OPFContactCopyEmailAddressList2"}
    assert {r["IsDefault"] for r in rows} == {"0", "1"} and {r["Type"] for r in rows} == {"work"}
    keys = [(r["record_key"], r["list_source"], r["list_ordinal"]) for r in rows]
    assert len(keys) == len(set(keys))


def test_record_keys_are_unique_and_scoped_to_the_archive(tmp_path: Path, built) -> None:
    archive, exp = built
    result, wb = run(tmp_path, archive)
    keys = [r["record_key"] for r in table_rows(wb, "contacts")]
    assert len(keys) == len(set(keys)) == exp.total_contacts
    assert all(k.startswith(result.input_sha256[:12] + "/") for k in keys)


@pytest.mark.parametrize("bad", ["999", "abc", ""], ids=["wrong-count", "not-a-number", "empty"])
def test_element_count_mismatch_is_not_structural(tmp_path: Path, bad: str) -> None:  # T27
    exp = Expect()
    xml = contacts_member(3, exp, "c.xml", element_count=bad)
    archive = write_zip(tmp_path / "a.olm", {"c.xml": xml})
    result, wb = run(tmp_path, archive)
    assert result.outcome is Outcome.PARTIAL and result.structural["elementCount"] == (0, 1)
    assert result.warnings_by_code == {"STRUCTURAL_MISMATCH": 1}
    raw = table_rows(wb, "raw_0001")
    assert [(r["attribute"], r["value"], r["element_path"]) for r in raw] == [("elementCount", bad, "/contacts[1]")]
    assert len(table_rows(wb, "contacts")) == 3  # the records themselves are unaffected


def test_invalid_xml_space_value_is_routed_to_raw(tmp_path: Path) -> None:  # T27
    exp = Expect()
    xml = contacts_member(2, exp, "c.xml").replace(b'<OPFContactCanEdit xml:space="preserve">', b'<OPFContactCanEdit xml:space="bogus">', 1)
    result, wb = run(tmp_path, write_zip(tmp_path / "a.olm", {"c.xml": xml}))
    assert result.structural["xml:space"][1] == 1
    raw = table_rows(wb, "raw_0001")
    assert [(r["attribute"], r["value"]) for r in raw] == [(XML_SPACE, "bogus")] and raw[0]["record_key"]
    assert result.outcome is Outcome.PARTIAL


def test_declared_names_on_the_wrong_element_are_never_structural(tmp_path: Path) -> None:  # T28
    exp = Expect()
    xml = contacts_member(1, exp, "c.xml", extra='<OPFContactCopyTitle xml:space="preserve" elementCount="5">x</OPFContactCopyTitle>')
    result, wb = run(tmp_path, write_zip(tmp_path / "a.olm", {"c.xml": xml}))
    assert [(r["attribute"], r["value"]) for r in table_rows(wb, "raw_0001")] == [("elementCount", "5")]
    assert result.structural["elementCount"] == (1, 0)  # only the root's


def test_unknown_elements_and_attributes_go_to_raw_with_the_record_key(tmp_path: Path) -> None:  # T33
    exp = Expect()
    extra = (
        f'<OPFContactCopyPronouns{SP}>they/them</OPFContactCopyPronouns>'
        f'<OPFContactCopyIMAddressList{SP}><contactEmailAddress{SP} OPFContactEmailAddressAddress="a@b.test" Extra="1"/></OPFContactCopyIMAddressList>'
    )
    xml = contacts_member(1, exp, "c.xml", picture_every=0, extra=extra)
    result, wb = run(tmp_path, write_zip(tmp_path / "a.olm", {"c.xml": xml}))
    raw = table_rows(wb, "raw_0001")
    assert {(r["element_path"].rsplit("/", 1)[-1], r["attribute"], r["value"]) for r in raw} == {
        ("OPFContactCopyPronouns[1]", "", "they/them"),
        ("contactEmailAddress[1]", "Extra", "1"),
    }
    assert all(r["record_key"].endswith("/1/1") for r in raw)
    assert result.outcome is Outcome.PARTIAL and result.totals.raw == 2
    assert [r["Address"] for r in table_rows(wb, "contact_emails") if r["list_source"] == "OPFContactCopyIMAddressList"] == ["a@b.test"]


def test_raw_extract_off_keeps_the_outcome_and_reports_lost(tmp_path: Path) -> None:  # T20
    exp = Expect()
    xml = contacts_member(1, exp, "c.xml", picture_every=0, extra=f'<OPFContactCopyPronouns{SP}>x</OPFContactCopyPronouns>')
    archive = write_zip(tmp_path / "a.olm", {"c.xml": xml})
    on, wb_on = run(tmp_path, archive)
    (tmp_path / "out" / "result.xlsx").unlink()
    off, wb_off = run(tmp_path, archive, raw_extract=False)
    assert on.outcome is off.outcome is Outcome.PARTIAL
    assert (on.totals.raw, on.totals.lost) == (1, 0) and (off.totals.raw, off.totals.lost) == (0, 1)
    assert off.lost_by_reason == {"RAW_EXTRACT_DISABLED": 1}
    assert "raw_0001" not in sheet_names(wb_off)


PIC = base64.b64encode(PNG_1X1).decode()


@pytest.mark.parametrize(
    ("extra", "pictures", "lost", "raw", "outcome"),
    [
        pytest.param(f"<OPFContactAddPicture{SP}>this is not base64 !!</OPFContactAddPicture><OPFContactAddPictureType{SP}>a</OPFContactAddPictureType>",
                     [("unknown", "text", False, "a")], 1, 0, Outcome.PARTIAL, id="not-base64-is-never-exported"),
        pytest.param(f"<OPFContactAddPicture{SP}>{PIC}</OPFContactAddPicture>",
                     [("base64", "decoded_bytes", True, "")], 0, 0, Outcome.SUCCESS, id="no-type-element"),
        pytest.param(f"<OPFContactAddPictureType{SP}>orphan</OPFContactAddPictureType>", [], 0, 1, Outcome.PARTIAL, id="type-without-picture"),
        pytest.param(f"<OPFContactAddPicture{SP}>{PIC}</OPFContactAddPicture><OPFContactAddPicture{SP}>{PIC}</OPFContactAddPicture>",
                     [("base64", "decoded_bytes", True, "")], 0, 1, Outcome.PARTIAL, id="second-picture-is-outside-the-known-shape"),
    ],
)
def test_pictures_that_do_not_decode_or_do_not_pair_are_reported_not_guessed(tmp_path: Path, extra, pictures, lost, raw, outcome) -> None:  # T31
    exp = Expect()
    xml = contacts_member(1, exp, "c.xml", picture_every=0, extra=extra)
    result, wb = run(tmp_path, write_zip(tmp_path / "a.olm", {"c.xml": xml}), export_images=True)
    rows = table_rows(wb, "contact_pictures")
    assert [(r["encoding"], r["hash_basis"], r["exported_file"] != "", r["type_declared"]) for r in rows] == pictures
    assert sum(result.lost_by_reason.values()) == lost and result.totals.raw == raw
    assert result.outcome is outcome


def test_contacts_are_claimed_by_content_not_by_name_or_path(tmp_path: Path) -> None:  # T34
    exp = Expect()
    good = contacts_member(2, exp, "weird/x.dat", picture_every=0)
    renamed = good.replace(b"<contacts", b"<people").replace(b"</contacts>", b"</people>")
    namespaced = good.replace(b"<contacts ", b'<contacts xmlns="urn:x" ', 1)
    archive = write_zip(tmp_path / "a.olm", {"weird/x.dat": good, "Contacts.xml": renamed, "ns/c.xml": namespaced})
    result, wb = run(tmp_path, archive)
    by_path = {m.path: m for m in result.members}
    assert by_path["weird/x.dat"].adapter_id == "contacts-olm-v1"
    assert by_path["Contacts.xml"].adapter_id == "" and by_path["ns/c.xml"].adapter_id == ""
    assert len(table_rows(wb, "contacts")) == 2
    raw_members = {r["archive_member_path"] for r in table_rows(wb, "raw_0001")}
    assert raw_members == {"Contacts.xml", "ns/c.xml"}


def test_schema_variants_never_succeed_silently(tmp_path: Path) -> None:  # T17, T18
    exp = Expect()
    good = contacts_member(2, exp, "c.xml", picture_every=0)
    renamed = good.replace(b"contactEmailAddress", b"emailAddress")
    result, wb = run(tmp_path, write_zip(tmp_path / "a.olm", {"c.xml": renamed}))
    assert result.outcome is Outcome.PARTIAL and len(table_rows(wb, "contact_emails")) == 0
    assert result.totals.raw > 0 and result.totals.source_values == len(reference_values(renamed))


def test_categories_adapter_rows(tmp_path: Path, built) -> None:
    archive, exp = built
    _, wb = run(tmp_path, archive)
    rows = table_rows(wb, "categories")
    assert [(r["source_member"], r["ordinal"], r["Name"]) for r in rows] == [(MEMBER_PATHS["categories"], str(k + 1), f"Global {k}") for k in range(exp.global_categories)]


def test_non_xml_members_make_the_result_partial_and_are_inventoried(tmp_path: Path) -> None:
    exp = Expect()
    archive = write_zip(tmp_path / "a.olm", {"c.xml": contacts_member(1, exp, "c.xml", picture_every=0, long_note_at=None), "blob.bin": b"\x00\x01\x02"})
    # Make every picture-free contact fully mapped so only the binary member prevents SUCCESS.
    result, wb = run(tmp_path, archive)
    assert result.outcome is Outcome.PARTIAL and result.totals.lost == 0 and result.totals.raw == 0
    assert [(r["path"], r["kind"]) for r in table_rows(wb, "_unsupported")] == [("blob.bin", "binary")]


def test_a_fully_mapped_archive_is_a_success(tmp_path: Path) -> None:
    exp = Expect()
    archive = write_zip(tmp_path / "a.olm", {"c.xml": contacts_member(3, exp, "c.xml", picture_every=0), "Categories.xml": categories_member(2, exp)})
    result, wb = run(tmp_path, archive)
    assert result.outcome is Outcome.SUCCESS and (result.totals.raw, result.totals.lost) == (0, 0)
    assert manifest(wb)["notice"] == "Fully converted."


def test_unsafe_and_corrupt_archives_fail_without_leaving_files(tmp_path: Path) -> None:
    bad = write_zip(tmp_path / "bad.olm", {"../evil.xml": b"<r/>"})
    result, _ = run(tmp_path, bad)
    assert result.outcome is Outcome.FAILED and result.error.code is ErrorCode.ARCHIVE_UNSAFE
    junk = tmp_path / "junk.olm"
    junk.write_bytes(b"not a zip")
    assert run(tmp_path, junk)[0].error.code is ErrorCode.INPUT_INVALID
    assert list((tmp_path / "out").iterdir()) == []


def test_existing_outputs_are_never_overwritten_by_default(tmp_path: Path, built) -> None:
    archive, _ = built
    run(tmp_path, archive)
    before = (tmp_path / "out" / "result.xlsx").read_bytes()
    second, _ = run(tmp_path, archive)
    assert second.outcome is Outcome.FAILED and second.error.code is ErrorCode.OUTPUT_IO
    assert (tmp_path / "out" / "result.xlsx").read_bytes() == before
    third, _ = run(tmp_path, archive, overwrite=True)
    assert third.outcome is Outcome.PARTIAL


def test_failed_verification_publishes_nothing(tmp_path: Path, built, monkeypatch: pytest.MonkeyPatch) -> None:
    from olm_excel.core import convert
    from olm_excel.core.errors import ConversionError

    def boom(path, expected):
        raise ConversionError(ErrorCode.OUTPUT_IO, "simulated verification failure")

    monkeypatch.setattr(convert, "verify_workbook", boom)
    archive, _ = built
    result, _ = run(tmp_path, archive, export_images=True)
    assert result.outcome is Outcome.FAILED
    assert list((tmp_path / "out").iterdir()) == []  # no workbook, no .partial files, no pictures directory


def test_oversized_cell_aborts_cleanly_with_an_excel_limit(tmp_path: Path) -> None:
    exp = Expect()
    xml = contacts_member(1, exp, "c.xml", picture_every=0)
    # A single enormous attribute value routed to raw is chunked, so this must still succeed.
    big = xml.replace(b"</contacts>", f'<OPFContactCopyPronouns{SP}>{"x" * 70_000}</OPFContactCopyPronouns></contacts>'.encode())
    result, wb = run(tmp_path, write_zip(tmp_path / "a.olm", {"c.xml": big}))
    chunks = [r for r in table_rows(wb, "raw_0001") if r["value_kind"] == "text"]
    assert result.outcome is Outcome.PARTIAL and any(int(r["chunk"]) == 3 for r in chunks)


BIG = "é" * 20_000 + "🙂" * 10_000  # 40,000 code points, 60,000 UTF-16 units


@pytest.mark.parametrize(
    ("extra", "sheet", "column", "field"),
    [
        pytest.param(f'<OPFContactCopyChildren{SP}><string{SP}>{BIG}</string></OPFContactCopyChildren>',
                     "contact_lists", "value", "contact_lists/OPFContactCopyChildren/1", id="list-string"),
        pytest.param(f'<OPFContactCopyIMAddressList{SP}><contactEmailAddress{SP} OPFContactEmailAddressAddress="{BIG}"/></OPFContactCopyIMAddressList>',
                     "contact_emails", "Address", "contact_emails/OPFContactCopyIMAddressList/1/Address", id="email-address"),
        pytest.param(f'<OPFContactCopyCategoryList{SP}><category{SP} OPFCategoryCopyName="{BIG}" OPFCategoryCopyBackgroundColor="#000"/></OPFContactCopyCategoryList>',
                     "contact_categories", "Name", "contact_categories/1/Name", id="category-name"),
        pytest.param(f'<OPFContactAddPicture{SP}>{PIC}</OPFContactAddPicture><OPFContactAddPictureType{SP}>{BIG}</OPFContactAddPictureType>',
                     "contact_pictures", "type_declared", "contact_pictures/1/type_declared", id="picture-type"),
    ],
)
def test_an_oversize_non_scalar_value_is_kept_not_fatal(tmp_path: Path, extra: str, sheet: str, column: str, field: str) -> None:
    exp = Expect()
    xml = contacts_member(1, exp, "c.xml", start=3, picture_every=0, extra=extra)  # contact 3 has no category or IM list of its own
    result, wb = run(tmp_path, write_zip(tmp_path / "a.olm", {"c.xml": xml}), export_images=True)
    assert result.error is None and result.outcome is not Outcome.FAILED
    assert result.totals.raw == 0 and result.totals.lost == 0 and result.outcome is Outcome.SUCCESS
    rows = [r for r in table_rows(wb, sheet) if r[column] and r[column].startswith("é")]
    assert len(rows) == 1
    chunks = {int(r["chunk"]): r["value"] for r in table_rows(wb, "contact_long_text") if r["field"] == field}
    assert rows[0][column] + "".join(chunks[k] for k in sorted(chunks)) == BIG
    assert len(rows[0][column].encode("utf-16-le")) // 2 <= 32_000 and min(chunks) == 2


def test_an_oversize_category_name_is_kept_on_its_own_sidecar(tmp_path: Path) -> None:
    xml = f'<categories elementCount="1"><category{SP} OPFCategoryCopyBackgroundColor="#111" OPFCategoryCopyName="{BIG}"/></categories>'.encode()
    result, wb = run(tmp_path, write_zip(tmp_path / "a.olm", {"Categories.xml": xml}))
    assert result.outcome is Outcome.SUCCESS
    (row,) = table_rows(wb, "categories")
    (chunk,) = table_rows(wb, "categories_long_text")
    assert row["Name"] + chunk["value"] == BIG and (chunk["field"], chunk["chunk"]) == ("Name", "2")


def test_a_failed_workbook_rename_publishes_neither_workbook_nor_pictures_and_keeps_the_old_workbook(
    tmp_path: Path, built, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, _ = built
    first, wb = run(tmp_path, archive)
    old = wb.read_bytes()

    import olm_excel.core.xlsx_writer as writer_module

    def refuse(src, dst):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(writer_module.os, "replace", refuse)
    result, _ = run(tmp_path, archive, export_images=True, overwrite=True)
    assert result.outcome is Outcome.FAILED and result.error.code is ErrorCode.OUTPUT_IO
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["result.xlsx"]  # no pictures dir, no .partial
    assert wb.read_bytes() == old  # the previous workbook survives a failed overwrite


def test_picture_message_lists_pictures_as_one_reason_among_others(tmp_path: Path) -> None:  # T35
    exp = Expect()
    extra = f"<OPFContactCopyPronouns{SP}>x</OPFContactCopyPronouns>"
    xml = contacts_member(4, exp, "c.xml", picture_every=2, extra=extra)
    result, wb = run(tmp_path, write_zip(tmp_path / "a.olm", {"c.xml": xml}))
    notice = manifest(wb)["notice"]
    assert result.outcome is Outcome.PARTIAL and result.totals.raw > 0 and exp.pictures == 2
    assert "only because" not in notice and "--export-images" not in notice
    assert notice.startswith("NOT FULLY CONVERTED (PARTIAL): ")
    assert "2 contact pictures were not exported (image export is off)" in notice
    assert f"{result.totals.raw} values kept as raw rows" in notice
    assert result.notice == notice


def test_no_picture_message_once_images_are_exported(tmp_path: Path, built) -> None:  # T35
    archive, _ = built
    result, wb = run(tmp_path, archive, export_images=True)
    assert result.outcome is Outcome.SUCCESS
    assert manifest(wb)["notice"] == result.notice == "Fully converted."


def test_undecodable_pictures_with_export_on_never_advise_export(tmp_path: Path) -> None:  # T35
    exp = Expect()
    extra = f"<OPFContactAddPicture{SP}>this is not base64 !!</OPFContactAddPicture>"
    xml = contacts_member(1, exp, "c.xml", picture_every=0, extra=extra)
    result, wb = run(tmp_path, write_zip(tmp_path / "a.olm", {"c.xml": xml}), export_images=True)
    notice = manifest(wb)["notice"]
    assert result.outcome is Outcome.PARTIAL and result.lost_by_reason == {"PICTURE_NOT_EXPORTED": 1}
    assert "only because" not in notice and "--export-images" not in notice
    assert "1 contact pictures could not be decoded, so were not exported" in notice


def test_cli_prints_the_picture_only_message(tmp_path: Path, built, capsys: pytest.CaptureFixture[str]) -> None:  # T35
    from olm_excel.interfaces import cli

    archive, exp = built
    code = cli.main(["convert", str(archive), "-o", str(tmp_path / "cli-out")])
    out = capsys.readouterr().out
    assert code == 3
    assert f"PARTIAL only because {exp.pictures} contact pictures were not exported." in out
