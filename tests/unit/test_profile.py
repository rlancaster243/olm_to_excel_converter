"""Structure-only profiler: no values, redacted names, correct structural counts."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from olm_excel.core.profile import SegmentRedactor, profile_archive
from olm_excel.core.walker import iter_source_values
from olm_excel.interfaces import cli

CONTACTS_MEMBER = "Accounts/test@example.com/Address Book/Contacts.xml"


def json_strings(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | set().union(*(json_strings(v) for v in obj.values()))
    if isinstance(obj, list):
        return set().union(*(json_strings(v) for v in obj)) if obj else set()
    return {obj} if isinstance(obj, str) else set()


@pytest.fixture(scope="module")
def sample_report(request) -> dict:
    return profile_archive(Path(__file__).resolve().parents[2] / "docs/samples/sample.olm")


def test_report_contains_no_source_value(sample_report: dict) -> None:
    with zipfile.ZipFile(Path(__file__).resolve().parents[2] / "docs/samples/sample.olm") as z:
        values = {v.value for v in iter_source_values(io.BytesIO(z.read(CONTACTS_MEMBER)))}
    leaked = json_strings(sample_report) & values
    assert not leaked, f"{len(leaked)} source values leaked into the report"
    assert sample_report["contains_values"] is False


def test_sample_structure_counts(sample_report: dict) -> None:
    (group,) = sample_report["member_groups"]
    assert group["member_pattern"].startswith("Accounts/~") and group["member_pattern"].endswith("/Address Book/Contacts.xml")
    xml = group["xml"]
    assert xml["source_values"] == 241_487 and xml["roots"] == {"/contacts": 1}
    paths = xml["paths"]
    assert paths["/contacts/contact"]["elements"] == 20_000
    emails = paths["/contacts/contact/OPFContactCopyEmailAddressList/emailAddress"]
    assert (emails["elements"], emails["max_sibling_index"]) == (25_864, 3)
    assert emails["attributes"]["OPFContactEmailAddressType"] == 25_864
    assert paths["/contacts/contact/OPFContactCopyNotesPlain"]["values_over_cell_cap"] == 1


class TestRedaction:
    redactor = SegmentRedactor(salt=b"fixed-test-salt!")

    @pytest.mark.parametrize(
        ("segment", "is_file", "expected"),
        [
            ("Address Book", False, "Address Book"),
            ("Contacts.xml", True, "Contacts.xml"),
            ("message_00012.xml", True, "message_#.xml"),
            ("Sent Items", False, "Sent Items"),
            ("4F3A9C2E-11D2-4B7A-9E10-ABCDEF012345.xml", True, "<id>.xml"),
            ("Contract Smith.pdf", True, "~file"),
            ("Q3 Board Notes.xml", True, "~file.xml"),
        ],
    )
    def test_segments(self, segment: str, is_file: bool, expected: str) -> None:
        assert self.redactor.segment(segment, is_file=is_file) == expected

    def test_personal_folder_names_are_hashed_consistently(self) -> None:
        a = self.redactor.segment("russell@example.org")
        assert a.startswith("~") and "russell" not in a
        assert a == self.redactor.segment("russell@example.org")
        assert a != SegmentRedactor(salt=b"another-salt-val").segment("russell@example.org")

    def test_show_names_keeps_everything(self) -> None:
        assert SegmentRedactor(reveal=True).path("Accounts/a@b.c/x.pdf") == "Accounts/a@b.c/x.pdf"


def _zip(tmp_path: Path, members: dict[str, bytes]) -> Path:
    path = tmp_path / "Outlook for Mac Archive.olm copy"  # extension must not matter
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return path


def test_member_types_unsafe_names_and_ratio_skip(tmp_path: Path) -> None:
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as z:
        z.writestr("inner.txt", "x")
    report = profile_archive(_zip(tmp_path, {
        "Local/a.xml": b"<?xml version='1.0'?><r><v>1</v></r>",
        "Local/b.bin": b"\x00\x01binary",
        "Local/c.zip": nested.getvalue(),
        "../escape.xml": b"<r/>",
        "Local/bomb.xml": b"<r>" + b" " * 5_000_000 + b"</r>",
    }))
    groups = {g["member_pattern"]: g for g in report["member_groups"]}
    assert report["unsafe_member_names"] == 1
    assert groups["Local/~file"]["types"] == {"binary": 1, "zip": 1}
    assert groups["Local/~file.xml"]["skipped"] == {"size_or_ratio_limit": 1}
    assert report["input"]["container"] == "zip"


def test_malformed_xml_is_counted_as_an_error_code_only(tmp_path: Path) -> None:
    report = profile_archive(_zip(tmp_path, {"Local/bad.xml": b"<r><a>secret-value</b></r>"}))
    (group,) = report["member_groups"]
    assert group["xml_errors"] == {"RECORD_PARSE_ERROR": 1}
    assert "secret-value" not in json.dumps(report)


def test_non_zip_input_is_reported_not_parsed(tmp_path: Path) -> None:
    path = tmp_path / "not-an-archive.olm"
    path.write_bytes(b"<contacts/>")
    report = profile_archive(path)
    assert report["error"].startswith("INPUT_INVALID") and "member_groups" not in report


def test_cli_profile_writes_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "profile.json"
    archive = _zip(tmp_path, {"Local/a.xml": b"<r><v>1</v></r>"})
    assert cli.main(["profile", str(archive), "-o", str(out)]) == 0
    assert json.loads(out.read_text())["totals"]["source_values"] == 1
    assert "structure only" in capsys.readouterr().out
