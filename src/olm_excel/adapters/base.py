"""Adapter contract (doc 04). An adapter maps one record family of one known layout."""

from __future__ import annotations

from typing import Protocol

from olm_excel.core.discovery import ProbeResult, XmlSignature
from olm_excel.core.member_context import MemberContext
from olm_excel.core.walker import SourceValue
from olm_excel.core.xlsx_writer import WorkbookWriter


class MemberSession(Protocol):
    """Consumes one member's source values in document order."""

    records_seen: int

    def feed(self, value: SourceValue) -> None: ...

    def finish(self) -> None:
        """Flush the record in progress. Called once, also after a mid-member error."""


class Adapter(Protocol):
    adapter_id: str
    adapter_version: str
    family: str
    structural: tuple[str, ...]  # names of core structural declarations this adapter opts into

    def probe(self, signature: XmlSignature) -> ProbeResult: ...

    def prepare(self, writer: WorkbookWriter) -> None:
        """Create this adapter's sheets. Called once, before the first member it claims."""

    def start(self, ctx: MemberContext) -> MemberSession: ...


def split_path(path: str) -> list[tuple[str, int]] | None:
    """'/a[1]/b[2]' -> [('a', 1), ('b', 2)]. None for paths the adapters do not handle (namespaced names)."""
    if "{" in path:
        return None
    segments: list[tuple[str, int]] = []
    for part in path[1:].split("/"):
        i = part.rfind("[")
        if i <= 0 or not part.endswith("]"):
            return None
        try:
            segments.append((part[:i], int(part[i + 1 : -1])))
        except ValueError:
            return None
    return segments
