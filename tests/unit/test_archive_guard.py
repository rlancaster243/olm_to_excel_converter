"""Archive guard: unsafe containers are rejected before any member is read (T10, F02)."""

from __future__ import annotations

import io
import warnings
import zipfile
from pathlib import Path

import pytest

from olm_excel.core.archive_guard import ArchiveLimits, SafeArchive
from olm_excel.core.errors import ConversionError, ErrorCode


def make_zip(tmp_path: Path, entries: dict[str, bytes], *, method: int = zipfile.ZIP_DEFLATED, name: str = "a.olm") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w", method) as z, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for entry, data in entries.items():
            z.writestr(entry, data)
    return path


def code_of(path: Path, limits: ArchiveLimits = ArchiveLimits()) -> ErrorCode:
    with pytest.raises(ConversionError) as exc:
        SafeArchive.open(path, limits)
    return exc.value.code


def test_inventory_orders_members_and_skips_directories(tmp_path: Path) -> None:
    path = make_zip(tmp_path, {"Accounts/": b"", "Accounts/a.xml": b"<r/>", "b.bin": b"\x00\x01"})
    with SafeArchive.open(path) as archive:
        inv = archive.inventory
        assert [(m.ordinal, m.path, m.size) for m in inv.members] == [(1, "Accounts/a.xml", 4), (2, "b.bin", 2)]
        assert len(inv.sha256) == 64 and inv.size_bytes == path.stat().st_size


@pytest.mark.parametrize(
    "name",
    ["../evil.xml", "a/../../evil.xml", "/abs.xml", "C:\\x.xml", "..\\evil.xml", "a\\..\\..\\b.xml", "ctl\x01char.xml"],
)
def test_unsafe_member_names_are_rejected(tmp_path: Path, name: str) -> None:
    assert code_of(make_zip(tmp_path, {"ok.xml": b"<r/>", name: b"<r/>"})) is ErrorCode.ARCHIVE_UNSAFE


def test_overlong_names_are_rejected(tmp_path: Path) -> None:
    assert code_of(make_zip(tmp_path, {"x" * 40: b"<r/>"}), ArchiveLimits(max_path_length=32)) is ErrorCode.ARCHIVE_UNSAFE


def test_symlinks_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "link.olm"
    with zipfile.ZipFile(path, "w") as z:
        info = zipfile.ZipInfo("link")
        info.external_attr = (0o120777 << 16)
        z.writestr(info, "/etc/passwd")
    assert code_of(path) is ErrorCode.ARCHIVE_UNSAFE


def test_duplicate_names_are_rejected_even_across_separator_styles(tmp_path: Path) -> None:
    assert code_of(make_zip(tmp_path, {"a/b.xml": b"1", "a\\b.xml": b"2"})) is ErrorCode.ARCHIVE_UNSAFE


@pytest.mark.parametrize(
    "limits",
    [
        ArchiveLimits(max_entries=1),
        ArchiveLimits(max_total_uncompressed=10),
        ArchiveLimits(max_member_uncompressed=10),
        ArchiveLimits(max_ratio=5),
    ],
    ids=["entries", "total", "member", "ratio"],
)
def test_resource_limits(tmp_path: Path, limits: ArchiveLimits) -> None:
    path = make_zip(tmp_path, {"a.xml": b"<r>" + b" " * 100_000 + b"</r>", "b.xml": b"<r/>"})
    assert code_of(path, limits) is ErrorCode.RESOURCE_LIMIT


def test_stored_members_have_ratio_one_and_pass_a_strict_ratio_limit(tmp_path: Path) -> None:
    path = make_zip(tmp_path, {"a.xml": b"<r>" + b" " * 100_000 + b"</r>"}, method=zipfile.ZIP_STORED)
    with SafeArchive.open(path, ArchiveLimits(max_ratio=2)) as archive:
        assert archive.inventory.members[0].ratio == 1.0


@pytest.mark.parametrize("content", [b"", b"not a zip at all", b"PK\x03\x04truncated"])
def test_non_zip_and_corrupt_inputs_are_input_invalid(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "bad.olm"
    path.write_bytes(content)
    assert code_of(path) is ErrorCode.INPUT_INVALID


def test_missing_and_directory_inputs_are_input_invalid(tmp_path: Path) -> None:
    assert code_of(tmp_path / "nope.olm") is ErrorCode.INPUT_INVALID
    assert code_of(tmp_path) is ErrorCode.INPUT_INVALID


def test_members_open_as_bounded_streams_and_sniff_by_content(tmp_path: Path) -> None:
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as z:
        z.writestr("inner.txt", "x")
    path = make_zip(tmp_path, {"data.dat": b"<?xml version='1.0'?><r/>", "pic.xml": b"\x89PNG\r\n", "n.zip": nested.getvalue(), "e": b""})
    with SafeArchive.open(path) as archive:
        kinds = {m.path: archive.sniff(m) for m in archive.inventory.members}
        assert kinds == {"data.dat": "xml", "pic.xml": "binary", "n.zip": "zip", "e": "empty"}  # names are never trusted
        with archive.open_member(archive.inventory.members[0]) as stream:
            assert stream.read() == b"<?xml version='1.0'?><r/>"


def test_corrupt_member_data_is_a_classified_error_not_a_crash(tmp_path: Path) -> None:
    path = make_zip(tmp_path, {"a.bin": bytes(range(256)) * 8}, method=zipfile.ZIP_STORED)
    raw = bytearray(path.read_bytes())
    raw[40] ^= 0xFF  # inside the stored data, so the CRC no longer matches
    path.write_bytes(bytes(raw))
    with SafeArchive.open(path) as archive, pytest.raises(ConversionError) as exc:
        with archive.open_member(archive.inventory.members[0]) as stream:
            stream.read()
    assert exc.value.code is ErrorCode.INPUT_INVALID


def test_encrypted_members_are_flagged_and_refused(tmp_path: Path) -> None:
    path = make_zip(tmp_path, {"secret.xml": b"<r/>"}, method=zipfile.ZIP_STORED, name="enc.olm")
    raw = bytearray(path.read_bytes())
    local, central = raw.index(b"PK\x03\x04"), raw.index(b"PK\x01\x02")
    raw[local + 6] |= 0x1  # general purpose flag bit 0: encrypted (ZipFile.writestr clears it, so patch the bytes)
    raw[central + 8] |= 0x1
    path.write_bytes(bytes(raw))
    with SafeArchive.open(path) as archive:
        (member,) = archive.inventory.members
        assert member.encrypted and archive.sniff(member) == "encrypted"
        with pytest.raises(ConversionError) as exc:
            archive.open_member(member)
        assert exc.value.code is ErrorCode.FORMAT_UNKNOWN


def test_the_guard_never_writes_next_to_the_input(tmp_path: Path) -> None:
    path = make_zip(tmp_path, {"a.xml": b"<r/>"})
    before = sorted(p.name for p in tmp_path.iterdir())
    with SafeArchive.open(path) as archive:
        for m in archive.inventory.members:
            with archive.open_member(m) as stream:
                stream.read()
    assert sorted(p.name for p in tmp_path.iterdir()) == before
