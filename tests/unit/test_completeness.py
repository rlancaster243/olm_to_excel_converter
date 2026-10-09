"""Field-level completeness rule and outcome (04 Completeness contract, F14)."""

from __future__ import annotations

import pytest

from olm_excel.core.completeness import MemberAccount, Outcome, decide_outcome, manifest_rows
from olm_excel.core.errors import ConversionError, ErrorCode


def account(source=10, mapped=0, raw=0, lost=0, counted=True) -> MemberAccount:
    a = MemberAccount("m.xml", source_values=source, mapped=mapped, raw=raw)
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
    assert [k for k, _ in rows[:6]] == ["outcome", "notice", "source_values", "mapped", "raw", "lost"]
    assert rows[0] == ("outcome", "PARTIAL")
    assert rows[1][1].startswith("NOT FULLY CONVERTED")
    assert dict(rows)["lost"] == "1"
