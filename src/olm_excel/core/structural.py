"""Structural value declarations (ADR-009, doc 04 "Structural values").

A structural value is format bookkeeping that is checked rather than exported.
Declarations are a closed list owned by the core. An adapter may only opt in
to declarations by name, and the core evaluates them, so an adapter cannot
declare record data structural. A value that matches a declaration but fails
its check is not structural.
"""

from __future__ import annotations

from dataclasses import dataclass

from olm_excel.core.walker import SourceValue, ValueKind

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


@dataclass(frozen=True, slots=True)
class StructuralDeclaration:
    name: str
    attribute: str  # Clark-notation attribute name
    depth: int | None  # None: any depth; 1: root element only
    roots: frozenset[str]  # empty: any root element
    evidence: str
    deferred: bool = False  # True: checked when the member ends, against the record count

    def matches(self, value: SourceValue, root: str) -> bool:
        return (
            value.value_kind is ValueKind.ATTRIBUTE
            and value.attribute == self.attribute
            and (self.depth is None or value.depth == self.depth)
            and (not self.roots or root in self.roots)
        )

    def check(self, value: str) -> bool:
        """Immediate validity check (non-deferred declarations)."""
        return value in ("preserve", "default") if self.attribute == XML_SPACE else False

    def check_count(self, value: str, records: int) -> bool:
        """Deferred check: the attribute must be a plain integer equal to the records parsed."""
        return value.isascii() and value.isdigit() and int(value) == records


DECLARATIONS: dict[str, StructuralDeclaration] = {
    d.name: d
    for d in (
        StructuralDeclaration(
            name="xml:space",
            attribute=XML_SPACE,
            depth=None,
            roots=frozenset(),
            evidence="E09: on every element of contacts members",
        ),
        StructuralDeclaration(
            name="elementCount",
            attribute="elementCount",
            depth=1,
            roots=frozenset({"contacts", "categories"}),
            evidence="E09: on the root element of every contacts and categories member",
            deferred=True,
        ),
    )
}
