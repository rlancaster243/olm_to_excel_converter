"""Synthetic archives that mirror the real export's structure (evidence E09), with fake values only.

The real archive is private. This builder reproduces its layout from the structure report: three
contacts members (account, folder, Local), a global Categories.xml, `xml:space` on every element,
`elementCount` on the roots, six `contactEmailAddress` containers and picture fields.
Expected counts come from the builder's own bookkeeping, independent of the code under test.
"""

from __future__ import annotations

import base64
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from olm_excel.adapters.contacts import EMAIL_CONTAINERS

SP = ' xml:space="preserve"'
# 1x1 transparent PNG: a real image, so magic-byte detection is exercised.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
LONG_NOTE = ("L" * 33_000) + "🙂" * 600  # 34,200 UTF-16 units: needs the long-text sheet

MEMBER_PATHS = {
    "main": "Accounts/acct-1/Contacts/Contacts.xml",
    "folder": "Accounts/acct-1/Contacts/folder-1/Contacts.xml",
    "local": "Local/Address Book/Contacts.xml",
    "categories": "Categories.xml",
}


@dataclass
class Expect:
    """What the builder wrote, counted as it wrote it."""

    contacts: dict[str, int] = field(default_factory=dict)  # member path -> contact count
    emails: int = 0
    category_rows: int = 0  # contact_categories rows
    list_rows: int = 0
    pictures: int = 0
    global_categories: int = 0
    structural: int = 0  # xml:space attributes + elementCount roots
    long_text_values: int = 0
    members_xml: dict[str, bytes] = field(default_factory=dict)

    @property
    def total_contacts(self) -> int:
        return sum(self.contacts.values())


def _el(tag: str, text: str | None = None, attrs: str = "") -> str:
    inner = "" if text is None else escape(text)
    return f"<{tag}{SP}{attrs}>{inner}</{tag}>"


def contact_xml(i: int, exp: Expect, *, with_picture: bool, long_note: bool, extra: str = "") -> str:
    parts = [
        _el("OPFContactCanDelete", "1"), _el("OPFContactCanEdit", "1"),
        _el("OPFContactCopyDisplayName", f"Person {i}"), _el("OPFContactCopyFirstName", f"First{i}"),
        _el("OPFContactCopyLastName", f"Last{i}"), _el("OPFContactCopyModDate", "2024-05-06T07:08:09"),
        _el("OPFContactCopyNotes", f"<html>note {i} &amp; more</html>"),
        _el("OPFContactCopyNotesPlain", LONG_NOTE if long_note else f"note {i}, with \"quotes\" & commas"),
        _el("OPFContactExchangeID", f"EX{i:08d}"), _el("OPFContactGetFlagStatus", "0"),
        _el("OPFContactIsJapaneseContact", "0"), _el("OPFContactType", "0"),
        _el("OPFContactCopyContactImage", f"img-{i}"),
    ]
    exp.structural += 14  # 13 field elements above + the contact element itself
    exp.long_text_values += int(long_note)
    if i % 2 == 0:
        parts.append(_el("OPFContactCopyBusinessPhone", "=SUM(A1:A9)" if i % 4 == 0 else "+44 20 1234 5678"))
        exp.structural += 1
    if i % 3 == 0:
        parts.append(_el("OPFContactCopyCellPhone", "0712 345678"))
        exp.structural += 1
    if i % 5 == 0:
        parts.append(_el("OPFContactCopyBirthday", "1975-03-12T00:00:00"))
        exp.structural += 1
    parts.append(_el("OPFContactCopyBusinessCompany", "Café Müller & Söhne 東京"))
    exp.structural += 1
    # Email containers: contact i uses the first (i % 3 + 1) of the six containers, i % 3 + 1 addresses in the list
    n_containers = i % 3 + 1
    for c, container in enumerate(EMAIL_CONTAINERS[:n_containers]):
        kids = []
        count = (i % 3 + 1) if c == 0 else 1
        for k in range(count):
            kids.append(
                f'<contactEmailAddress{SP} OPFContactEmailAddressAddress={quoteattr(f"p{i}.{c}.{k}@example.test")}'
                f' OPFContactEmailAddressIsDefault="{1 if k == 0 else 0}" OPFContactEmailAddressType="work"/>'
            )
            exp.emails += 1
            exp.structural += 1
        parts.append(f"<{container}{SP}>{''.join(kids)}</{container}>")
        exp.structural += 1
    # Categories: list + primary
    cats = [f'<category{SP} OPFCategoryCopyBackgroundColor="#FF{k:04d}" OPFCategoryCopyName={quoteattr(f"Cat {k}")}/>' for k in range(i % 3)]
    if cats:
        parts.append(f"<OPFContactCopyCategoryList{SP}>{''.join(cats)}</OPFContactCopyCategoryList>")
        exp.category_rows += len(cats)
        exp.structural += 1 + len(cats)
        parts.append(
            f"<OPFContactCopyPrimaryCategory{SP}>{_el('OPFCategoryCopyBackgroundColor', '#FF0000')}"
            f"{_el('OPFCategoryCopyName', 'Cat 0')}</OPFContactCopyPrimaryCategory>"
        )
        exp.structural += 3
    if i % 7 == 0:
        parts.append(f"<OPFContactCopyChildren{SP}>{_el('string', f'Kid {i}')}</OPFContactCopyChildren>")
        exp.list_rows += 1
        exp.structural += 2
    if with_picture:
        parts.append(_el("OPFContactAddPicture", base64.b64encode(PNG_1X1).decode()))
        parts.append(_el("OPFContactAddPictureType", "image/png"))
        exp.pictures += 1
        exp.structural += 2
    parts.append(extra)
    return f"<contact{SP}>{''.join(parts)}</contact>"


def contacts_member(count: int, exp: Expect, path: str, *, start: int = 1, picture_every: int = 4, long_note_at: int | None = None,
                    element_count: str | None = None, root_extra: str = "", extra: str = "") -> bytes:
    body = "".join(
        contact_xml(i, exp, with_picture=(picture_every and i % picture_every == 0), long_note=(i == long_note_at), extra=extra)
        for i in range(start, start + count)
    )
    exp.contacts[path] = count
    exp.structural += 2  # root xml:space + root elementCount
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<contacts{SP} elementCount="{count if element_count is None else element_count}"{root_extra}>{body}</contacts>'
    return xml.encode("utf-8")


def categories_member(count: int, exp: Expect) -> bytes:
    rows = "".join(
        f'<category{SP} OPFCategoryCopyBackgroundColor="#00{k:04d}" OPFCategoryCopyName={quoteattr(f"Global {k}")}/>' for k in range(count)
    )
    exp.global_categories = count
    exp.structural += count + 1  # one xml:space per category + root elementCount (this root has no xml:space)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<categories elementCount="{count}">{rows}</categories>'.encode("utf-8")


def build_archive(path: Path, *, counts: tuple[int, int, int] = (6, 3, 1), categories: int = 4, **member_kwargs) -> Expect:
    """Write a real-layout archive and return what it holds. Member order matches the real export's profile."""
    exp = Expect()
    members = {
        MEMBER_PATHS["main"]: contacts_member(counts[0], exp, MEMBER_PATHS["main"], long_note_at=2, **member_kwargs),
        MEMBER_PATHS["folder"]: contacts_member(counts[1], exp, MEMBER_PATHS["folder"], start=105, **member_kwargs),
        MEMBER_PATHS["categories"]: categories_member(categories, exp),
        MEMBER_PATHS["local"]: contacts_member(counts[2], exp, MEMBER_PATHS["local"], start=200, **member_kwargs),
    }
    exp.members_xml = dict(members)
    write_zip(path, members)
    return exp


def write_zip(path: Path, members: dict[str, bytes], method: int = zipfile.ZIP_STORED) -> Path:
    with zipfile.ZipFile(path, "w", method) as z:  # the real export stores members uncompressed
        for name, data in members.items():
            z.writestr(name, data)
    return path
