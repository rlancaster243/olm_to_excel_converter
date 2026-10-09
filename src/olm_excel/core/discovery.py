"""Content-based discovery of XML members (ADR-002, F03).

Adapters are selected by what a member contains, never by its path or file
name. A member is claimed only when exactly one adapter reports high
confidence; conflicting or low-confidence probes claim nothing and the member
goes to the raw extractor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol

import defusedxml.ElementTree as SafeET

from olm_excel.core.errors import ConversionError, ErrorCode

_MAX_GRANDCHILDREN = 16


@dataclass(frozen=True, slots=True)
class XmlSignature:
    """What the start of an XML member looks like. Names only, never values."""

    root: str = ""
    root_attributes: tuple[str, ...] = ()
    child: str = ""
    child_attributes: tuple[str, ...] = ()
    grandchildren: tuple[str, ...] = ()  # element names inside the first child


@dataclass(frozen=True, slots=True)
class ProbeResult:
    adapter_id: str
    confident: bool
    reason: str


class Probe(Protocol):
    adapter_id: str

    def probe(self, signature: XmlSignature) -> ProbeResult: ...


def sniff_signature(stream: BinaryIO) -> XmlSignature:
    """Read just enough of the member to fingerprint it (root, first record and its children)."""
    root = child = ""
    root_attrs: tuple[str, ...] = ()
    child_attrs: tuple[str, ...] = ()
    grandchildren: list[str] = []
    depth = 0
    try:
        for event, el in SafeET.iterparse(stream, events=("start", "end")):
            if event == "start":
                depth += 1
                if depth == 1:
                    root, root_attrs = el.tag, tuple(sorted(el.attrib))
                elif depth == 2:
                    if child:
                        break  # second record reached: the first one is fully described
                    child, child_attrs = el.tag, tuple(sorted(el.attrib))
                elif depth == 3 and len(grandchildren) < _MAX_GRANDCHILDREN:
                    grandchildren.append(el.tag)
            else:
                depth -= 1
                if depth == 1 and child:
                    break
    except ConversionError:
        raise
    except Exception as exc:  # malformed or unsafe XML: fingerprint what we have, the walker reports the error
        if not root:
            raise ConversionError(ErrorCode.RECORD_PARSE_ERROR, f"cannot fingerprint member: {type(exc).__name__}") from exc
    return XmlSignature(root, root_attrs, child, child_attrs, tuple(grandchildren))


def select_adapter(signature: XmlSignature, adapters: list) -> tuple[object | None, list[ProbeResult]]:
    """Return the single confident adapter, or None when nothing or more than one matches."""
    results = [a.probe(signature) for a in adapters]
    confident = [(a, r) for a, r in zip(adapters, results) if r.confident]
    if len(confident) == 1:
        return confident[0][0], results
    return None, results
