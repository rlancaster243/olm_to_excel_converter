"""The core settles every source value; an adapter cannot grade its own coverage (T24)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from olm_excel.core.completeness import MemberAccount
from olm_excel.core.errors import ConversionError, ErrorCode
from olm_excel.core.member_context import MemberContext, StructuralStats, WarningLog
from olm_excel.core.raw_extract import RawExtractor, XmlMember
from olm_excel.core.walker import ValueKind, iter_source_values
from olm_excel.core.xlsx_writer import WorkbookWriter
from tests.helpers import read_rows

XML = b'<contacts xml:space="preserve" elementCount="2"><contact><a>1</a><b>2</b></contact><contact><a>3</a></contact></contacts>'


def make_ctx(tmp_path: Path, *, enabled: bool = True):
    writer = WorkbookWriter(tmp_path / "t.xlsx")
    extractor = RawExtractor(writer, submission_id="s", enabled=enabled)
    member = XmlMember(1, "m.xml", lambda: io.BytesIO(XML))
    account = MemberAccount("m.xml")
    warnings = WarningLog()
    ctx = MemberContext(member=member, account=account, extractor=extractor, allowed_structural=("xml:space", "elementCount"),
                        stats=StructuralStats(), warnings=warnings, archive_id="arch")
    return writer, extractor, ctx, account, warnings


def drive(ctx, on_value) -> None:
    for value in ctx.values(iter_source_values(io.BytesIO(XML))):
        on_value(value)


def test_an_adapter_that_settles_nothing_is_swept_to_raw_with_a_warning(tmp_path: Path) -> None:
    writer, extractor, ctx, account, warnings = make_ctx(tmp_path)
    drive(ctx, lambda v: None)  # forgets every value
    ctx.finish(records_seen=2)
    extractor.finish()
    assert account.source_values == 5 and account.raw == 5 and account.reconciles()  # nothing silently dropped
    assert warnings.totals_by_code() == {"ADAPTER_UNREPORTED": 5}
    writer.publish()
    assert len(read_rows(tmp_path / "t.xlsx", "raw_0001")) == 6


def test_a_value_is_swept_to_raw_only_after_its_record_ends(tmp_path: Path) -> None:
    writer, extractor, ctx, account, _ = make_ctx(tmp_path)
    seen: list[int] = []

    def on_value(v):
        if ctx.check_structural(v):
            return
        seen.append(account.raw)
        ctx.mapped(v)

    drive(ctx, on_value)
    ctx.finish(records_seen=2)
    assert account.mapped == 3 and account.structural == 2 and account.raw == 0 and seen == [0, 0, 0]
    writer.abort()


def test_settling_a_value_twice_is_an_internal_error(tmp_path: Path) -> None:
    writer, _, ctx, _, _ = make_ctx(tmp_path)
    with pytest.raises(ConversionError) as exc:
        drive(ctx, lambda v: (ctx.mapped(v), ctx.mapped(v)))
    assert exc.value.code is ErrorCode.INTERNAL_ERROR
    writer.abort()


def test_only_declared_values_can_be_structural(tmp_path: Path) -> None:
    writer, _, ctx, account, _ = make_ctx(tmp_path)
    drive(ctx, lambda v: ctx.check_structural(v) or ctx.mapped(v))
    ctx.finish(records_seen=2)
    assert account.structural == 2  # xml:space on the root and the root elementCount, nothing else
    assert all(
        v.value_kind is not ValueKind.ATTRIBUTE or v.attribute in ("elementCount", "{http://www.w3.org/XML/1998/namespace}space")
        for v in iter_source_values(io.BytesIO(XML))
    )
    writer.abort()


def test_unknown_declaration_names_are_rejected(tmp_path: Path) -> None:
    writer = WorkbookWriter(tmp_path / "t.xlsx")
    with pytest.raises(ValueError):
        MemberContext(member=XmlMember(1, "m", lambda: io.BytesIO(b"")), account=MemberAccount("m"),
                      extractor=RawExtractor(writer, submission_id="s"), allowed_structural=("everything",),
                      stats=StructuralStats(), warnings=WarningLog(), archive_id="a")
    writer.abort()


def test_with_raw_extract_off_unreported_values_are_lost_not_dropped(tmp_path: Path) -> None:
    writer, extractor, ctx, account, _ = make_ctx(tmp_path, enabled=False)
    drive(ctx, lambda v: None)
    ctx.finish(records_seen=2)
    assert account.lost[ErrorCode.RAW_EXTRACT_DISABLED] == 5 and account.reconciles()
    writer.abort()
