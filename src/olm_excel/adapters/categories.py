"""Global category list adapter, `categories-olm-v1` (doc 04 Contacts v1 contract, evidence E09)."""

from __future__ import annotations

from olm_excel.adapters.base import split_path
from olm_excel.core.discovery import ProbeResult, XmlSignature
from olm_excel.core.member_context import MemberContext
from olm_excel.core.walker import SourceValue, ValueKind
from olm_excel.core.xlsx_writer import CHUNK_UTF16, Table, WorkbookWriter, chunk_utf16, utf16_len

NAME = "OPFCategoryCopyName"
COLOR = "OPFCategoryCopyBackgroundColor"
HEADER = ("source_member", "ordinal", "Name", "BackgroundColor")
LONG_TEXT_HEADER = ("source_member", "ordinal", "field", "chunk", "value")


class CategoriesAdapter:
    adapter_id = "categories-olm-v1"
    adapter_version = "1.0.0"
    family = "category"
    structural = ("xml:space", "elementCount")

    def __init__(self) -> None:
        self._writer: WorkbookWriter | None = None
        self._table: Table | None = None
        self._long_text: Table | None = None

    @property
    def long_text(self) -> Table:
        if self._long_text is None:
            self._long_text = self._writer.add_table("categories_long_text", LONG_TEXT_HEADER, spill=True)
        return self._long_text

    @staticmethod
    def expected_structure() -> dict[str, set[str]]:
        """Collapsed element path -> attribute names this adapter accounts for (used by conformance tests)."""
        return {
            "/categories": {"elementCount", "{http://www.w3.org/XML/1998/namespace}space"},
            "/categories/category": {NAME, COLOR, "{http://www.w3.org/XML/1998/namespace}space"},
        }

    def probe(self, signature: XmlSignature) -> ProbeResult:
        ok = (
            signature.root == "categories"
            and signature.child == "category"
            and {NAME, COLOR} <= set(signature.child_attributes)
        )
        reason = "root categories, category records with name and colour attributes" if ok else "structure does not match"
        return ProbeResult(self.adapter_id, ok, reason)

    def prepare(self, writer: WorkbookWriter) -> None:
        self._writer = writer
        self._table = writer.add_table("categories", HEADER, spill=True)

    def start(self, ctx: MemberContext) -> _Session:
        return _Session(self, ctx)


class _Session:
    def __init__(self, adapter: CategoriesAdapter, ctx: MemberContext) -> None:
        self._adapter = adapter
        self._table = adapter._table
        self._ctx = ctx
        self._n = 0
        self._attrs: dict[str, str] = {}
        self.records_seen = 0

    def feed(self, value: SourceValue) -> None:
        ctx = self._ctx
        segs = split_path(value.element_path)
        if segs is None or segs[0][0] != "categories":
            ctx.unknown(value)
            return
        if len(segs) == 1:
            if not (value.value_kind is ValueKind.ATTRIBUTE and ctx.check_structural(value)):
                ctx.unknown(value)
            return
        if segs[1][0] != "category":
            ctx.unknown(value)
            return
        n = segs[1][1]
        if n != self._n:
            self._flush()
            self._n = n
            self._attrs = {}
        if len(segs) == 2 and value.value_kind is ValueKind.ATTRIBUTE:
            if value.attribute in (NAME, COLOR):
                self._attrs[value.attribute] = value.value
                ctx.mapped(value)
                return
            if ctx.check_structural(value):
                return
        ctx.unknown(value, ctx.record_key(n))

    def _flush(self) -> None:
        if not self._n:
            return
        member, ordinal = self._ctx.member.path, str(self._n)
        cells = []
        for label, attribute in (("Name", NAME), ("BackgroundColor", COLOR)):
            text = self._attrs.get(attribute, "")
            if len(text) > CHUNK_UTF16 // 2 and utf16_len(text) > CHUNK_UTF16:
                text, *rest = chunk_utf16(text)
                for number, chunk in enumerate(rest, start=2):
                    self._adapter.long_text.append((member, ordinal, label, str(number), chunk))
            cells.append(text)
        self._table.append((member, ordinal, *cells))
        self.records_seen += 1
        self._ctx.end_record(self._ctx.record_key(self._n))

    def finish(self) -> None:
        self._flush()
        self._n = 0
