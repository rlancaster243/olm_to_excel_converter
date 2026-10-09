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


def test_cli_convert_not_implemented_yet(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["convert", "x.olm"]) == 2
    assert "not implemented" in capsys.readouterr().err
