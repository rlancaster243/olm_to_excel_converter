"""The adapters account for every element path and attribute in the real export's structure report (E09).

`docs/samples/olm-profile.contacts-archive.json` was produced by `olm-excel profile` on the owner's own
export: names and counts only. This test needs no private data and fails if the real layout has
anything the adapters do not handle.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from olm_excel.adapters.categories import CategoriesAdapter
from olm_excel.adapters.contacts import SCALAR_ELEMENTS, ContactsAdapter

PROFILE = Path(__file__).resolve().parents[2] / "docs/samples/olm-profile.contacts-archive.json"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


@pytest.fixture(scope="module")
def groups() -> list[dict]:
    report = json.loads(PROFILE.read_text())
    assert report["contains_values"] is False
    return [g for g in report["member_groups"] if "xml" in g]


def adapter_for(root: str) -> dict[str, set[str]]:
    return {"/contacts": ContactsAdapter, "/categories": CategoriesAdapter}[root].expected_structure()


def test_every_real_path_and_attribute_is_handled(groups: list[dict]) -> None:
    unhandled: list[str] = []
    for group in groups:
        (root,) = group["xml"]["roots"]
        expected = adapter_for(root)
        for path, stats in group["xml"]["paths"].items():
            if path not in expected:
                unhandled.append(path)
                continue
            extra = set(stats.get("attributes", {})) - expected[path]
            if extra:
                unhandled.append(f"{path} @{sorted(extra)}")
    assert unhandled == []


def test_the_real_layout_has_three_contacts_members_and_one_categories_member(groups: list[dict]) -> None:
    roots = sorted(next(iter(g["xml"]["roots"])) for g in groups)
    assert roots == ["/categories", "/contacts", "/contacts", "/contacts"]


def test_the_closed_scalar_list_matches_the_real_leaf_fields(groups: list[dict]) -> None:
    leaves: set[str] = set()
    for group in groups:
        if "/contacts" not in group["xml"]["roots"]:
            continue
        for path, stats in group["xml"]["paths"].items():
            parts = path.split("/")
            if len(parts) == 4 and parts[1:3] == ["contacts", "contact"] and (stats.get("text_values") or stats.get("empty_values")):
                leaves.add(parts[3])
    pictures = {"OPFContactAddPicture", "OPFContactAddPictureType"}
    # Leaves that are containers' children (e.g. a text-bearing wrapper) would not appear at depth 4; everything
    # that does appear must be a scalar column or a picture field.
    assert leaves - pictures <= set(SCALAR_ELEMENTS)
    assert set(SCALAR_ELEMENTS) - leaves == set()  # and every listed scalar really occurs in the real export


def test_real_values_per_path_fit_the_cell_policy(groups: list[dict]) -> None:
    over = {
        p: s["values_over_cell_cap"]
        for g in groups
        for p, s in g["xml"]["paths"].items()
        if s.get("values_over_cell_cap")
    }
    assert over == {"/contacts/contact/OPFContactAddPicture": 12}  # only pictures exceed the cap, so only they need file export
