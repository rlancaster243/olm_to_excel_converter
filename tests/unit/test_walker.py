"""Source-value walker: 04 Source values definition (T09, T21, T22)."""

from __future__ import annotations

import io
import random

import pytest

from olm_excel.core.errors import ConversionError, ErrorCode
from olm_excel.core.walker import ValueKind, WalkLimits, iter_source_values
from tests.helpers import reference_values


def walk(xml: bytes, **limits):
    return list(iter_source_values(io.BytesIO(xml), WalkLimits(**limits)))


def triples(values):
    return [(v.value_kind.value, v.attribute, v.value) for v in values]


def test_mixed_content_keeps_tail_text_with_parent_paths_and_positions() -> None:
    values = walk(b"<r><n a='1'>Hi <b>Bob</b> thanks<i/> end</n></r>")
    assert [(v.value_kind, v.value, v.text_position, v.element_path) for v in values] == [
        (ValueKind.ATTRIBUTE, "1", None, "/r[1]/n[1]"),
        (ValueKind.TEXT, "Hi ", 0, "/r[1]/n[1]"),
        (ValueKind.TEXT, "Bob", 0, "/r[1]/n[1]/b[1]"),
        (ValueKind.TEXT, " thanks", 1, "/r[1]/n[1]"),  # belongs to <n>, not <b>
        (ValueKind.EMPTY, "", None, "/r[1]/n[1]/i[1]"),
        (ValueKind.TEXT, " end", 2, "/r[1]/n[1]"),
    ]
    assert [v.node_ordinal for v in values] == list(range(1, 7))


def test_whitespace_rules() -> None:
    xml = (
        b"<r>\n  <leaf> </leaf>\n  <fmt>\n    <c>x</c>\n  </fmt>"
        b"<keep xml:space='preserve'> <c/> </keep><none/><attrs k='v'/></r>"
    )
    assert triples(walk(xml)) == [
        ("text", "", " "),  # whitespace-only leaf text is a value
        ("text", "", "x"),  # formatting whitespace around <c> is not
        ("attribute", "{http://www.w3.org/XML/1998/namespace}space", "preserve"),
        ("text", "", " "),  # preserved whitespace before the first child
        ("empty", "", ""),
        ("text", "", " "),  # preserved tail
        ("empty", "", ""),  # truly empty element
        ("attribute", "k", "v"),  # attributes only: no empty row
    ]


def test_namespace_declarations_are_not_values_and_paths_use_clark_notation() -> None:
    values = walk(b"<r xmlns='urn:x' xmlns:p='urn:p'><p:k p:z='q'/></r>")
    assert [(v.attribute, v.value, v.element_path) for v in values] == [
        ("{urn:p}z", "q", "/{urn:x}r[1]/{urn:p}k[1]"),
    ]


def test_positional_index_counts_same_tag_siblings_only() -> None:
    values = walk(b"<r><a>1</a><b>2</b><a>3</a></r>")
    assert [v.element_path for v in values] == ["/r[1]/a[1]", "/r[1]/b[1]", "/r[1]/a[2]"]


def _random_doc(rng: random.Random, depth: int = 0) -> str:
    parts = []
    for _ in range(rng.randint(0, 4)):
        tag = rng.choice(["a", "b", "c"])
        attrs = "".join(f' {k}="{rng.randint(0, 9)}"' for k in rng.sample(["x", "y"], rng.randint(0, 2)))
        space = ' xml:space="preserve"' if rng.random() < 0.1 else ""
        inner = _random_doc(rng, depth + 1) if depth < 4 and rng.random() < 0.6 else rng.choice(["", " ", "t", "  w  "])
        parts.append(f"<{tag}{attrs}{space}>{inner}</{tag}>" + rng.choice(["", " ", "\n  ", "tail"]))
    return rng.choice(["", " ", "lead"]) + "".join(parts)


@pytest.mark.parametrize("seed", range(25))
def test_streaming_matches_whole_document_reference(seed: int) -> None:
    rng = random.Random(seed)
    # iterparse delivers events in batches, so a walker that clears an element at its
    # own end event loses tail text here (mutation-checked: 27 of these cases fail).
    xml = ("<root>" + "".join(f"<item n='{i}'>{_random_doc(rng)}</item>" for i in range(400)) + "</root>").encode()
    assert triples(walk(xml)) == reference_values(xml)


def test_entity_declarations_are_rejected_as_unsafe() -> None:
    xml = b'<!DOCTYPE r [<!ENTITY e "boom">]><r>&e;</r>'
    with pytest.raises(ConversionError) as exc:
        walk(xml)
    assert exc.value.code is ErrorCode.ARCHIVE_UNSAFE


def test_external_entities_are_rejected_as_unsafe() -> None:
    xml = b'<!DOCTYPE r [<!ENTITY e SYSTEM "file:///etc/passwd">]><r>&e;</r>'
    with pytest.raises(ConversionError) as exc:
        walk(xml)
    assert exc.value.code is ErrorCode.ARCHIVE_UNSAFE


def test_depth_limit() -> None:
    with pytest.raises(ConversionError) as exc:
        walk(b"<a>" * 10 + b"</a>" * 10, max_depth=5)
    assert exc.value.code is ErrorCode.RESOURCE_LIMIT


def test_malformed_xml_keeps_values_seen_before_the_error() -> None:
    seen = []
    with pytest.raises(ConversionError) as exc:
        for value in iter_source_values(io.BytesIO(b"<r><a>1</a><b>2</b><c>3</d></r>")):
            seen.append(value.value)
    assert exc.value.code is ErrorCode.RECORD_PARSE_ERROR
    assert seen[:2] == ["1", "2"]
