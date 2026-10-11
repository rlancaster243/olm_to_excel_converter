"""W01 smoke tests: the package imports and the CLI stub behaves."""

from __future__ import annotations

import pytest

import olm_excel
from olm_excel.interfaces import cli


def test_version_is_set() -> None:
    assert olm_excel.__version__ == "0.0.1"


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "0.0.1" in capsys.readouterr().out


def test_cli_convert_reports_a_missing_input_as_failed(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["convert", str(tmp_path / "missing.olm"), "-o", str(tmp_path / "out")]) == 1
    out = capsys.readouterr().out
    assert "FAILED" in out and "INPUT_INVALID" in out


def test_safe_stem_is_path_safe_nonempty_and_unique() -> None:
    from pathlib import Path

    taken: set[str] = set()
    names = ["Outlook for Mac Archive.olm copy", "../../etc/passwd", "....olm", "Outlook for Mac Archive.olm copy"]
    stems = [cli.safe_stem(Path(n), taken) for n in names]
    assert stems == ["Outlook_for_Mac_Archive", "passwd", "archive", "Outlook_for_Mac_Archive-2"]
    assert all("/" not in s and ".." not in s for s in stems)


def test_cli_convert_exit_codes_and_summary(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    from tests.real_layout import Expect, categories_member, contacts_member, write_zip

    exp = Expect()
    full = write_zip(tmp_path / "full.olm", {"c.xml": contacts_member(2, exp, "c.xml", picture_every=0), "Categories.xml": categories_member(1, exp)})
    pics = write_zip(tmp_path / "pics.olm", {"c.xml": contacts_member(2, exp, "c.xml", picture_every=1)})
    out = tmp_path / "out"
    assert cli.main(["convert", str(full), "-o", str(out)]) == 0
    assert cli.main(["convert", str(pics), "-o", str(out)]) == 3  # pictures not exported
    assert cli.main(["convert", str(pics), "-o", str(out), "--export-images"]) == 1  # workbook already exists
    assert cli.main(["convert", str(pics), "-o", str(out), "--export-images", "--overwrite"]) == 0
    text = capsys.readouterr().out
    assert "full.olm: SUCCESS" in text and "pics.olm: PARTIAL" in text and "lost PICTURE_NOT_EXPORTED: 2" in text
    assert "pictures: 1 files" in text
    assert "PARTIAL only because 2 contact pictures were not exported. Re-run with image export (--export-images)" in text
    assert "c.xml" not in text  # member paths are not echoed to the terminal
