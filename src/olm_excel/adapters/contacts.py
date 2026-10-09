"""Contacts adapter, `contacts-olm-v1` (doc 04 Contacts v1 contract, evidence E09).

Maps the contacts layout observed in one real export. The scalar field list is
closed: any element or attribute not listed here is an unknown field and goes to
the raw extract, so a different layout is never mapped by guesswork (ADR-007).
Every value is written as exact source text (ADR-011).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass, field
from typing import Protocol

from olm_excel.adapters.base import split_path
from olm_excel.core.discovery import ProbeResult, XmlSignature
from olm_excel.core.errors import ErrorCode
from olm_excel.core.member_context import MemberContext
from olm_excel.core.walker import SourceValue, ValueKind
from olm_excel.core.xlsx_writer import CHUNK_UTF16, Table, WorkbookWriter, chunk_utf16, utf16_len

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

# Closed list of scalar record fields, verbatim element names (E09, 56 names).
SCALAR_ELEMENTS: tuple[str, ...] = (
    "OPFContactCanDelete", "OPFContactCanEdit", "OPFContactCopyAge", "OPFContactCopyAnniversary",
    "OPFContactCopyAssistantPhone", "OPFContactCopyBirthday", "OPFContactCopyBusinessCity",
    "OPFContactCopyBusinessCompany", "OPFContactCopyBusinessCountry", "OPFContactCopyBusinessDepartment",
    "OPFContactCopyBusinessFax", "OPFContactCopyBusinessHomePage", "OPFContactCopyBusinessOffice",
    "OPFContactCopyBusinessPhone", "OPFContactCopyBusinessPhone2", "OPFContactCopyBusinessState",
    "OPFContactCopyBusinessStreetAddress", "OPFContactCopyBusinessTitle", "OPFContactCopyBusinessZip",
    "OPFContactCopyCellPhone", "OPFContactCopyContactImage", "OPFContactCopyDisplayName",
    "OPFContactCopyFirstName", "OPFContactCopyFuriganaFirstName", "OPFContactCopyFuriganaLastName",
    "OPFContactCopyHomeCity", "OPFContactCopyHomeCountry", "OPFContactCopyHomeFax", "OPFContactCopyHomePhone",
    "OPFContactCopyHomePhone2", "OPFContactCopyHomeState", "OPFContactCopyHomeStreetAddress",
    "OPFContactCopyHomeWebPage", "OPFContactCopyHomeZip", "OPFContactCopyLastName", "OPFContactCopyMiddleName",
    "OPFContactCopyModDate", "OPFContactCopyNickName", "OPFContactCopyNotes", "OPFContactCopyNotesPlain",
    "OPFContactCopyOtherCity", "OPFContactCopyOtherCountry", "OPFContactCopyOtherPhone",
    "OPFContactCopyOtherState", "OPFContactCopyOtherStreetAddress", "OPFContactCopyOtherZip",
    "OPFContactCopyPager", "OPFContactCopyRadioPhone", "OPFContactCopySetNameSuffix",
    "OPFContactCopySpousesName", "OPFContactCopyTitle", "OPFContactExchangeID", "OPFContactGetFlagStatus",
    "OPFContactIsJapaneseContact", "OPFContactMainPhone", "OPFContactType",
)
PICTURE = "OPFContactAddPicture"
PICTURE_TYPE = "OPFContactAddPictureType"
EMAIL_CONTAINERS: tuple[str, ...] = (
    "OPFContactCopyEmailAddressList", "OPFContactCopyEmailAddressList1", "OPFContactCopyEmailAddressList2",
    "OPFContactCopyDefaultEmailAddress", "OPFContactCopyIMAddressList", "OPFContactCopyDefaultIMAddress",
)
EMAIL_ELEMENT = "contactEmailAddress"
EMAIL_ATTRS = ("OPFContactEmailAddressAddress", "OPFContactEmailAddressIsDefault", "OPFContactEmailAddressType")
CATEGORY_LIST = "OPFContactCopyCategoryList"
CATEGORY_ATTRS = ("OPFCategoryCopyName", "OPFCategoryCopyBackgroundColor")
PRIMARY_CATEGORY = "OPFContactCopyPrimaryCategory"
LIST_CONTAINERS: tuple[str, ...] = ("OPFContactCopyChildren", "OPFContactCopyFuriganaChildrensNames")
LIST_ELEMENT = "string"


def column_names(elements: tuple[str, ...] = SCALAR_ELEMENTS) -> dict[str, str]:
    """Element name -> column name: drop a leading OPFContactCopy, else OPFContact. Collisions keep verbatim names."""
    short = {e: (e.removeprefix("OPFContactCopy") if e.startswith("OPFContactCopy") else e.removeprefix("OPFContact")) for e in elements}
    counts: dict[str, int] = {}
    for name in short.values():
        counts[name] = counts.get(name, 0) + 1
    return {e: (name if counts[name] == 1 else e) for e, name in short.items()}


COLUMNS = column_names()
CONTACTS_HEADER = (
    "record_key", "source_member", "contact_ordinal",
    *(COLUMNS[e] for e in SCALAR_ELEMENTS),
    "PrimaryCategory_Name", "PrimaryCategory_BackgroundColor", "empty_fields",
)
EMAILS_HEADER = ("record_key", "list_source", "list_ordinal", "Address", "IsDefault", "Type")
CATEGORIES_HEADER = ("record_key", "ordinal", "Name", "BackgroundColor")
LISTS_HEADER = ("record_key", "list_source", "ordinal", "value")
PICTURES_HEADER = (
    "record_key", "picture_ordinal", "type_declared", "encoding", "size_chars", "decoded_bytes",
    "detected_format", "hash_basis", "sha256", "exported_file",
)
LONG_TEXT_HEADER = ("record_key", "field", "chunk", "value")

DEFAULT_MAX_PICTURE_BYTES = 128 * 1024**2
_WHITESPACE = re.compile(r"\s+")


class PictureSink(Protocol):
    def write(self, sha256: str, extension: str, data: bytes) -> str:
        """Store one image and return the path to record in `exported_file`."""


def detect_image_format(data: bytes) -> str:
    """Name an image format from its leading magic bytes only. No image library is involved."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"msf1"):
        return "heic"
    if data.startswith(b"BM") and len(data) > 14:
        return "bmp"
    return "unknown"


_EXTENSIONS = {"jpeg": "jpg"}


@dataclass(slots=True)
class _Record:
    ordinal: int
    scalars: dict[str, str] = field(default_factory=dict)
    empty: list[str] = field(default_factory=list)
    primary: dict[str, str] = field(default_factory=dict)
    emails: dict[tuple[str, int], dict[str, str]] = field(default_factory=dict)
    categories: dict[int, dict[str, str]] = field(default_factory=dict)
    lists: dict[tuple[str, int], str] = field(default_factory=dict)
    pictures: list[SourceValue] = field(default_factory=list)
    picture_types: list[SourceValue] = field(default_factory=list)


class ContactsAdapter:
    adapter_id = "contacts-olm-v1"
    adapter_version = "1.0.0"
    family = "contact"
    structural = ("xml:space", "elementCount")

    def __init__(self, picture_sink: PictureSink | None = None, max_picture_bytes: int = DEFAULT_MAX_PICTURE_BYTES) -> None:
        self.picture_sink = picture_sink
        self.max_picture_bytes = max_picture_bytes
        self._writer: WorkbookWriter | None = None
        self.contacts: Table | None = None
        self.emails: Table | None = None
        self.categories: Table | None = None
        self.lists: Table | None = None
        self.pictures: Table | None = None
        self._long_text: Table | None = None

    @staticmethod
    def expected_structure() -> dict[str, set[str]]:
        """Collapsed element path -> attribute names this adapter accounts for (used by conformance tests)."""
        base = "/contacts/contact"
        out: dict[str, set[str]] = {"/contacts": {"elementCount", XML_SPACE}, base: {XML_SPACE}}
        for e in (*SCALAR_ELEMENTS, PICTURE, PICTURE_TYPE):
            out[f"{base}/{e}"] = {XML_SPACE}
        for c in EMAIL_CONTAINERS:
            out[f"{base}/{c}"] = {XML_SPACE}
            out[f"{base}/{c}/{EMAIL_ELEMENT}"] = {*EMAIL_ATTRS, XML_SPACE}
        out[f"{base}/{CATEGORY_LIST}"] = {XML_SPACE}
        out[f"{base}/{CATEGORY_LIST}/category"] = {*CATEGORY_ATTRS, XML_SPACE}
        out[f"{base}/{PRIMARY_CATEGORY}"] = {XML_SPACE}
        for a in CATEGORY_ATTRS:
            out[f"{base}/{PRIMARY_CATEGORY}/{a}"] = {XML_SPACE}
        for c in LIST_CONTAINERS:
            out[f"{base}/{c}"] = {XML_SPACE}
            out[f"{base}/{c}/{LIST_ELEMENT}"] = {XML_SPACE}
        return out

    def probe(self, signature: XmlSignature) -> ProbeResult:
        ok = (
            signature.root == "contacts"
            and signature.child == "contact"
            and bool(signature.grandchildren)
            and all(name.startswith("OPFContact") for name in signature.grandchildren)
        )
        reason = "root contacts, contact records with OPFContact* fields" if ok else "structure does not match"
        return ProbeResult(self.adapter_id, ok, reason)

    def prepare(self, writer: WorkbookWriter) -> None:
        self._writer = writer
        self.contacts = writer.add_table("contacts", CONTACTS_HEADER, spill=True)
        self.emails = writer.add_table("contact_emails", EMAILS_HEADER, spill=True)
        self.categories = writer.add_table("contact_categories", CATEGORIES_HEADER, spill=True)
        self.lists = writer.add_table("contact_lists", LISTS_HEADER, spill=True)
        self.pictures = writer.add_table("contact_pictures", PICTURES_HEADER, spill=True)

    @property
    def long_text(self) -> Table:
        if self._long_text is None:
            self._long_text = self._writer.add_table("contact_long_text", LONG_TEXT_HEADER, spill=True)
        return self._long_text

    def start(self, ctx: MemberContext) -> _Session:
        return _Session(self, ctx)


class _Session:
    def __init__(self, adapter: ContactsAdapter, ctx: MemberContext) -> None:
        self._a = adapter
        self._ctx = ctx
        self._rec: _Record | None = None
        self.records_seen = 0

    # ---- routing -------------------------------------------------------------------------------
    def feed(self, value: SourceValue) -> None:
        ctx = self._ctx
        segs = split_path(value.element_path)
        if segs is None or segs[0] != ("contacts", 1):
            ctx.unknown(value)
            return
        if len(segs) == 1:  # the root element
            if not (value.value_kind is ValueKind.ATTRIBUTE and ctx.check_structural(value)):
                ctx.unknown(value)
            return
        if segs[1][0] != "contact":
            ctx.unknown(value)
            return
        n = segs[1][1]
        if self._rec is None or n != self._rec.ordinal:
            self._flush()
            self._rec = _Record(n)
        rec = self._rec
        key = ctx.record_key(n)
        kind = value.value_kind
        attribute = kind is ValueKind.ATTRIBUTE
        if attribute and value.attribute == XML_SPACE and ctx.check_structural(value):
            return
        depth = len(segs)
        if depth == 3:
            tag, idx = segs[2]
            if tag == PICTURE and kind is ValueKind.TEXT:  # every text value is a picture, any index
                rec.pictures.append(value)  # settled at flush, once the encoding is known
                return
            if tag == PICTURE_TYPE and kind is ValueKind.TEXT:  # paired at flush only
                rec.picture_types.append(value)
                return
            if idx == 1 and not attribute and (kind is ValueKind.EMPTY or value.text_position == 0):
                if tag in COLUMNS:
                    rec.scalars[tag] = value.value
                    if kind is ValueKind.EMPTY:
                        rec.empty.append(COLUMNS[tag])
                    ctx.mapped(value)
                    return
        elif depth == 4:
            container, cidx = segs[2]
            child, child_idx = segs[3]
            if cidx == 1:
                if container in EMAIL_CONTAINERS and child == EMAIL_ELEMENT and attribute and value.attribute in EMAIL_ATTRS:
                    rec.emails.setdefault((container, child_idx), {})[value.attribute] = value.value
                    ctx.mapped(value)
                    return
                if container == CATEGORY_LIST and child == "category" and attribute and value.attribute in CATEGORY_ATTRS:
                    rec.categories.setdefault(child_idx, {})[value.attribute] = value.value
                    ctx.mapped(value)
                    return
                if container == PRIMARY_CATEGORY and child in CATEGORY_ATTRS and child_idx == 1 and not attribute:
                    rec.primary[child] = value.value
                    ctx.mapped(value)
                    return
                if container in LIST_CONTAINERS and child == LIST_ELEMENT and not attribute and (
                    kind is ValueKind.EMPTY or value.text_position == 0
                ):
                    rec.lists[(container, child_idx)] = value.value
                    ctx.mapped(value)
                    return
        ctx.unknown(value, key)

    # ---- projection ----------------------------------------------------------------------------
    def _flush(self) -> None:
        rec = self._rec
        if rec is None:
            return
        ctx, a = self._ctx, self._a
        key = ctx.record_key(rec.ordinal)
        fit = self._fit
        cells = [fit(key, COLUMNS[e], rec.scalars.get(e, "")) for e in SCALAR_ELEMENTS]
        a.contacts.append((
            key, ctx.member.path, str(rec.ordinal), *cells,
            fit(key, "PrimaryCategory_Name", rec.primary.get(CATEGORY_ATTRS[0], "")),
            fit(key, "PrimaryCategory_BackgroundColor", rec.primary.get(CATEGORY_ATTRS[1], "")),
            "; ".join(rec.empty),
        ))
        for (container, idx), attrs in rec.emails.items():
            a.emails.append((
                key, container, str(idx),
                *(fit(key, f"contact_emails/{container}/{idx}/{col}", attrs.get(name, ""))
                  for name, col in zip(EMAIL_ATTRS, ("Address", "IsDefault", "Type"))),
            ))
        for idx, attrs in rec.categories.items():
            a.categories.append((
                key, str(idx),
                fit(key, f"contact_categories/{idx}/Name", attrs.get(CATEGORY_ATTRS[0], "")),
                fit(key, f"contact_categories/{idx}/BackgroundColor", attrs.get(CATEGORY_ATTRS[1], "")),
            ))
        for (container, idx), text in rec.lists.items():
            a.lists.append((key, container, str(idx), fit(key, f"contact_lists/{container}/{idx}", text)))
        self._flush_pictures(rec, key)
        self.records_seen += 1
        ctx.end_record(key)
        self._rec = None

    def _fit(self, key: str, label: str, text: str) -> str:
        """Return the text for a cell. A value over the cell cap keeps its first chunk here and the
        rest on `contact_long_text` (`field` names the column), so no value can fail the archive."""
        if len(text) <= CHUNK_UTF16 // 2 or utf16_len(text) <= CHUNK_UTF16:
            return text
        first, *rest = chunk_utf16(text)
        for number, chunk in enumerate(rest, start=2):
            self._a.long_text.append((key, label, str(number), chunk))
        return first

    def _flush_pictures(self, rec: _Record, key: str) -> None:
        ctx, a = self._ctx, self._a
        declared = ""
        if len(rec.pictures) == 1 and len(rec.picture_types) == 1:  # pair only exactly one of each
            declared = rec.picture_types[0].value
            ctx.mapped(rec.picture_types[0])
        else:
            for stray in rec.picture_types:
                ctx.unknown(stray, key)
        for number, picture in enumerate(rec.pictures, start=1):
            text = picture.value
            decoded: bytes | None = None
            if len(text) <= self._a.max_picture_bytes * 4 // 3 + 8:
                try:
                    decoded = base64.b64decode(_WHITESPACE.sub("", text), validate=True) or None
                except (binascii.Error, ValueError):
                    decoded = None
            if decoded is not None:
                encoding, fmt, basis = "base64", detect_image_format(decoded), "decoded_bytes"
                digest, size = hashlib.sha256(decoded).hexdigest(), str(len(decoded))
            else:
                encoding, fmt, basis, size = "unknown", "", "text", ""
                digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
            exported = ""
            if decoded is not None and a.picture_sink is not None:
                exported = a.picture_sink.write(digest, _EXTENSIONS.get(fmt, fmt) if fmt != "unknown" else "bin", decoded)
            a.pictures.append((key, str(number), self._fit(key, f"contact_pictures/{number}/type_declared", declared), encoding, str(len(text)), size, fmt, basis, digest, exported))
            if exported:
                ctx.mapped(picture)
            else:
                ctx.lost(picture, ErrorCode.PICTURE_NOT_EXPORTED)

    def finish(self) -> None:
        self._flush()
