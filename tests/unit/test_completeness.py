"""Field-level completeness rule and outcome (04 Completeness contract, F14)."""

from __future__ import annotations

import pytest

from olm_excel.core.completeness import MemberAccount, Outcome, decide_outcome, manifest_rows, outcome_notice
from olm_excel.core.errors import ConversionError, ErrorCode


def account(source=10, mapped=0, raw=0, lost=0, counted=True, structural=0) -> MemberAccount:
    a = MemberAccount("m.xml", source_values=source, mapped=mapped, structural=structural, raw=raw)
    if lost:
        a.add_lost(ErrorCode.RAW_EXTRACT_LIMIT, lost)
    if not counted:
        a.mark_uncounted(ErrorCode.RECORD_PARSE_ERROR)
    return a


def test_success_requires_every_value_mapped() -> None:
    assert decide_outcome([account(mapped=10)], families_converted=1) is Outcome.SUCCESS


@pytest.mark.parametrize("acct", [account(mapped=9, raw=1), account(mapped=9, lost=1), account(source=10, mapped=10, counted=False)])
def test_any_raw_lost_or_uncounted_value_prevents_success(acct: MemberAccount) -> None:
    assert decide_outcome([acct], families_converted=1) is Outcome.PARTIAL


def test_structural_values_count_toward_success_but_must_reconcile() -> None:
    assert decide_outcome([account(mapped=6, structural=4)], families_converted=1) is Outcome.SUCCESS
    with pytest.raises(ConversionError):
        decide_outcome([account(mapped=6, structural=3)], families_converted=1)


def test_picture_not_exported_is_a_loss_reason_that_prevents_success() -> None:
    a = account(mapped=9)
    a.add_lost(ErrorCode.PICTURE_NOT_EXPORTED)
    assert decide_outcome([a], families_converted=1) is Outcome.PARTIAL


def test_no_converted_family_is_unsupported_even_if_complete() -> None:
    assert decide_outcome([account(raw=10)], families_converted=0) is Outcome.UNSUPPORTED
    assert decide_outcome([], families_converted=0) is Outcome.UNSUPPORTED  # T15: no empty success


def test_unclaimed_non_xml_member_prevents_success() -> None:
    assert decide_outcome([account(mapped=10)], families_converted=1, unclaimed_non_xml_members=1) is Outcome.PARTIAL


def test_outcome_is_identical_whether_unmapped_values_are_raw_or_lost() -> None:
    as_raw = decide_outcome([account(mapped=5, raw=5)], families_converted=1)
    as_lost = decide_outcome([account(mapped=5, lost=5)], families_converted=1)
    assert as_raw is as_lost is Outcome.PARTIAL


def test_counters_that_do_not_reconcile_are_an_internal_error() -> None:
    with pytest.raises(ConversionError) as exc:
        decide_outcome([account(source=10, mapped=3)], families_converted=1)
    assert exc.value.code is ErrorCode.INTERNAL_ERROR


def test_only_defined_loss_reasons_are_accepted() -> None:
    with pytest.raises(ValueError):
        MemberAccount("m").add_lost(ErrorCode.CANCELLED)


def test_manifest_leads_with_outcome_notice_and_counts() -> None:
    rows = manifest_rows(Outcome.PARTIAL, [account(mapped=7, raw=2, lost=1)], raw_extract=True)
    assert [k for k, _ in rows[:7]] == ["outcome", "notice", "source_values", "mapped", "structural", "raw", "lost"]
    assert rows[0] == ("outcome", "PARTIAL")
    assert rows[1][1].startswith("NOT FULLY CONVERTED")
    assert dict(rows)["lost"] == "1"


def test_manifest_lists_refused_members_when_given() -> None:
    rows = manifest_rows(Outcome.PARTIAL, [], raw_extract=True, refused_members=[("bad.xml", "ARCHIVE_UNSAFE")])
    assert dict(rows)["refused_members"] == "bad.xml:ARCHIVE_UNSAFE"


def picture_account(pictures: int = 3, raw: int = 0, counted: bool = True) -> MemberAccount:
    a = MemberAccount("c.xml", source_values=10 + pictures + raw, mapped=10, raw=raw)
    a.add_lost(ErrorCode.PICTURE_NOT_EXPORTED, pictures)
    if not counted:
        a.mark_uncounted(ErrorCode.RECORD_PARSE_ERROR)
    return a


class TestOutcomeNotice:  # T35
    def test_picture_only_names_the_fix(self) -> None:
        assert outcome_notice(Outcome.PARTIAL, [picture_account()]) == (
            "PARTIAL only because 3 contact pictures were not exported. "
            "Re-run with image export (--export-images) to include them."
        )

    @pytest.mark.parametrize(
        "kwargs, acct",
        [
            pytest.param({}, picture_account(raw=1), id="raw-values"),
            pytest.param({}, picture_account(counted=False), id="uncounted-member"),
            pytest.param({"unclaimed_non_xml_members": 1}, picture_account(), id="non-xml-member"),
            pytest.param({"warning_codes": ["STRUCTURAL_MISMATCH"]}, picture_account(), id="warning"),
        ],
    )
    def test_any_other_reason_removes_the_only_because_wording(self, kwargs, acct) -> None:
        notice = outcome_notice(Outcome.PARTIAL, [acct], **kwargs)
        assert "only because" not in notice and "--export-images" not in notice
        assert "3 contact pictures were not exported (image export is off)" in notice

    def test_other_lost_reasons_are_listed_alongside_pictures(self) -> None:
        acct = picture_account()
        acct.source_values += 2
        acct.add_lost(ErrorCode.RAW_EXTRACT_DISABLED, 2)
        notice = outcome_notice(Outcome.PARTIAL, [acct])
        assert "only because" not in notice and "2 values lost (RAW_EXTRACT_DISABLED)" in notice

    def test_export_already_on_never_advises_export(self) -> None:
        notice = outcome_notice(Outcome.PARTIAL, [picture_account()], images_exported=True)
        assert "only because" not in notice and "--export-images" not in notice
        assert "3 contact pictures could not be decoded" in notice

    def test_unsupported_never_uses_the_picture_only_wording(self) -> None:
        assert "only because" not in outcome_notice(Outcome.UNSUPPORTED, [picture_account()])

    def test_success_is_fully_converted(self) -> None:
        assert outcome_notice(Outcome.SUCCESS, [account(mapped=10)]) == "Fully converted (count-conserving)."
