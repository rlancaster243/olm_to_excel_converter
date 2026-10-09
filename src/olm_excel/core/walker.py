"""Core source-value walker (W04).

Contract: docs/fidelity/04-CONTRACTS-AND-DATA.md, "Source values".
Adapters and the raw extractor read XML members through this walker, so
source values are counted once, independently of any adapter.

A source value is one of:
- an attribute value (namespace declarations are not attributes here);
- a text node that contains non-whitespace, or that is whitespace-only
  inside an element with no child elements, or anywhere under
  ``xml:space="preserve"``;
- an empty element: no attributes, no children, no text at all.

Comments and processing instructions are not source values.

Streaming: memory stays bounded by depth, not by member size (ADR-004).
Each element is detached and cleared once its parent has read its tail
text (at the next sibling's start or the parent's end). Clearing an
element at its own end event would lose that tail, because iterparse
reports events in batches and the tail may already be set by then.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import BinaryIO
from xml.etree.ElementTree import Element, ParseError

import defusedxml
import defusedxml.ElementTree as SafeET

from olm_excel.core.errors import ConversionError, ErrorCode

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


class ValueKind(StrEnum):
    ATTRIBUTE = "attribute"
    TEXT = "text"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class SourceValue:
    node_ordinal: int  # 1-based, document order within the member
    element_path: str  # Clark-notation positional path of the containing element
    value_kind: ValueKind
    value: str
    attribute: str = ""  # qualified attribute name, attribute rows only
    text_position: int | None = None  # text rows only: 0 = before first child, k = after k-th child


@dataclass(frozen=True, slots=True)
class WalkLimits:
    max_depth: int = 256


@dataclass(slots=True)
class _Frame:
    element: Element
    path: str
    preserve: bool
    child_count: int = 0
    last_child: Element | None = None
    child_tags: dict[str, int] = field(default_factory=dict)


def _release(frame: _Frame) -> None:
    """Free the frame's last child after its tail text has been read."""
    child = frame.last_child
    frame.element.remove(child)
    child.clear()
    frame.last_child = None


def iter_source_values(member: BinaryIO, limits: WalkLimits = WalkLimits()) -> Iterator[SourceValue]:
    """Yield every source value of one XML member, in document order.

    Values already yielded stay valid if a ConversionError is raised later
    (malformed or unsafe content): callers keep them and mark the member
    incomplete.
    """
    ordinal = 0
    stack: list[_Frame] = []

    def text_value(frame: _Frame, text: str | None, position: int, has_children: bool) -> SourceValue | None:
        nonlocal ordinal
        if not text:
            return None
        if not text.strip() and has_children and not frame.preserve:
            return None  # formatting whitespace between child elements
        ordinal += 1
        return SourceValue(ordinal, frame.path, ValueKind.TEXT, text, text_position=position)

    try:
        for event, element in SafeET.iterparse(member, events=("start", "end")):
            if event == "start":
                parent = stack[-1] if stack else None
                if parent is None:
                    path, preserve = f"/{element.tag}[1]", False
                else:
                    if parent.child_count == 0:
                        value = text_value(parent, parent.element.text, 0, has_children=True)
                    else:
                        value = text_value(parent, parent.last_child.tail, parent.child_count, has_children=True)
                        _release(parent)
                    if value is not None:
                        yield value
                    parent.child_count += 1
                    index = parent.child_tags[element.tag] = parent.child_tags.get(element.tag, 0) + 1
                    path, preserve = f"{parent.path}/{element.tag}[{index}]", parent.preserve
                space = element.get(XML_SPACE)
                if space == "preserve":
                    preserve = True
                elif space == "default":
                    preserve = False
                if len(stack) >= limits.max_depth:
                    raise ConversionError(ErrorCode.RESOURCE_LIMIT, f"element depth exceeds {limits.max_depth}")
                frame = _Frame(element, path, preserve)
                stack.append(frame)
                for name, attr_value in element.attrib.items():
                    ordinal += 1
                    yield SourceValue(ordinal, path, ValueKind.ATTRIBUTE, attr_value, attribute=name)
            else:
                frame = stack.pop()
                if frame.child_count == 0:
                    value = text_value(frame, element.text, 0, has_children=False)
                    if value is not None:
                        yield value
                    elif not element.attrib:
                        ordinal += 1
                        yield SourceValue(ordinal, frame.path, ValueKind.EMPTY, "")
                else:
                    value = text_value(frame, frame.last_child.tail, frame.child_count, has_children=True)
                    _release(frame)
                    if value is not None:
                        yield value
                if stack:
                    # Not cleared yet: iterparse reports events in batches, so this
                    # element's tail may already be set. The parent reads the tail
                    # first, then releases the element (see _release).
                    stack[-1].last_child = element
                else:
                    element.clear()
    except defusedxml.DefusedXmlException as exc:
        raise ConversionError(ErrorCode.ARCHIVE_UNSAFE, f"forbidden XML construct: {type(exc).__name__}") from exc
    except ParseError as exc:
        raise ConversionError(ErrorCode.RECORD_PARSE_ERROR, f"malformed XML at line {exc.position[0]}") from exc


def count_source_values(member: BinaryIO, limits: WalkLimits = WalkLimits()) -> int:
    """Return the number of source values in one XML member stream."""
    return sum(1 for _ in iter_source_values(member, limits))
