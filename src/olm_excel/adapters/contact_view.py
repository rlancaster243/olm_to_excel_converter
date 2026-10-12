"""Readable `Contact list` sheet: a presentation view of contacts-olm-v1 records (04, Contact list view).

The view copies values that the adapter has already settled on the audited sheets (`contacts`,
`contact_emails`, `contact_categories`, `contact_lists`, `contact_pictures`). It is not counted: completeness
is proven on those sheets, and each view row links back to them through `Source ref` (the record_key).

What the view does to make rows readable, and nothing else:
- friendly column names in a people-first order; system fields are left out;
- emails in Email 1-3, the default address first, exact repeats within one contact shown once, the rest in
  `More emails`; IM addresses are kept apart in `IM`;
- each address as one cell: street, city, state zip, country;
- `Notes` from NotesPlain, else Notes;
- a value over the cell cap is cut at 32,000 UTF-16 units with a marker (the full text is on the audited sheets).
Values are otherwise exact source text, dates included (ADR-011). Nothing is inferred.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from olm_excel.core.xlsx_writer import CHUNK_UTF16, chunk_utf16, utf16_len

_P = "OPFContactCopy"
IM_CONTAINERS = frozenset({f"{_P}IMAddressList", f"{_P}DefaultIMAddress"})
_TRUE = frozenset({"1", "true", "yes"})
MAX_EMAIL_COLUMNS = 3
TRUNCATED = " [cut here; full text on the contacts sheets]"

# (column name, width). Order is the sheet order.
VIEW_COLUMNS: tuple[tuple[str, float], ...] = (
    ("Name", 28), ("First name", 16), ("Last name", 18), ("Nickname", 14),
    ("Company", 26), ("Job title", 24), ("Department", 18), ("Office", 14),
    ("Email 1", 32), ("Email 2", 32), ("Email 3", 32), ("More emails", 40),
    ("Mobile", 18), ("Work phone", 18), ("Work phone 2", 18), ("Home phone", 18), ("Home phone 2", 18),
    ("Main phone", 18), ("Other phone", 18), ("Assistant phone", 18), ("Work fax", 18), ("Home fax", 18),
    ("Pager", 14), ("Radio phone", 14), ("IM", 28),
    ("Work address", 45), ("Home address", 45), ("Other address", 45),
    ("Work website", 30), ("Personal website", 30),
    ("Birthday", 14), ("Anniversary", 14), ("Spouse", 18), ("Children", 24),
    ("Categories", 28), ("Notes", 50), ("Picture", 20), ("Source ref", 22),
)
VIEW_HEADER: tuple[str, ...] = tuple(name for name, _ in VIEW_COLUMNS)
VIEW_WIDTHS: tuple[float, ...] = tuple(width for _, width in VIEW_COLUMNS)

# View column -> source element, for the one-to-one columns.
_SCALAR_COLUMNS: dict[str, str] = {
    "First name": "FirstName", "Last name": "LastName", "Nickname": "NickName",
    "Company": "BusinessCompany", "Job title": "BusinessTitle", "Department": "BusinessDepartment",
    "Office": "BusinessOffice", "Mobile": "CellPhone", "Work phone": "BusinessPhone",
    "Work phone 2": "BusinessPhone2", "Home phone": "HomePhone", "Home phone 2": "HomePhone2",
    "Main phone": "OPFContactMainPhone", "Other phone": "OtherPhone", "Assistant phone": "AssistantPhone",
    "Work fax": "BusinessFax", "Home fax": "HomeFax", "Pager": "Pager", "Radio phone": "RadioPhone",
    "Work website": "BusinessHomePage", "Personal website": "HomeWebPage",
    "Birthday": "Birthday", "Anniversary": "Anniversary", "Spouse": "SpousesName",
}


def _element(name: str) -> str:
    return name if name.startswith("OPFContact") else _P + name


def _nonempty(parts: Iterable[str]) -> list[str]:
    return [p for p in (s.strip() for s in parts) if p]


def _one_line(text: str) -> str:
    return ", ".join(_nonempty(text.replace("\r\n", "\n").replace("\r", "\n").split("\n")))


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        k = v.strip().casefold()
        if k and k not in seen:
            seen.add(k)
            out.append(v.strip())
    return out


def fit_cell(text: str) -> str:
    """Keep a view cell under Excel's cap; the full value stays on the audited sheets."""
    if len(text) <= CHUNK_UTF16 // 2 or utf16_len(text) <= CHUNK_UTF16:
        return text
    return chunk_utf16(text)[0] + TRUNCATED


def address(scalars: Mapping[str, str], kind: str) -> str:
    g = lambda field: scalars.get(f"{_P}{kind}{field}", "")  # noqa: E731
    return ", ".join(_nonempty([_one_line(g("StreetAddress")), g("City"), " ".join(_nonempty([g("State"), g("Zip")])), g("Country")]))


def display_name(scalars: Mapping[str, str]) -> str:
    shown = scalars.get(f"{_P}DisplayName", "").strip()
    if shown:
        return shown
    return " ".join(_nonempty(scalars.get(f"{_P}{f}", "") for f in ("FirstName", "MiddleName", "LastName", "SetNameSuffix")))


def split_emails(emails: Sequence[tuple[str, Mapping[str, str]]]) -> tuple[list[str], list[str]]:
    """(email addresses, IM addresses). Input is document order; default addresses move to the front."""
    mail = [(c, a) for c, a in emails if c not in IM_CONTAINERS]
    im = [a.get("OPFContactEmailAddressAddress", "") for c, a in emails if c in IM_CONTAINERS]
    default = [a for _, a in mail if a.get("OPFContactEmailAddressIsDefault", "").strip().lower() in _TRUE]
    rest = [a for _, a in mail if a.get("OPFContactEmailAddressIsDefault", "").strip().lower() not in _TRUE]
    ordered = [a.get("OPFContactEmailAddressAddress", "") for a in (*default, *rest)]
    return _unique(ordered), _unique(im)


def view_row(
    *,
    record_key: str,
    scalars: Mapping[str, str],
    emails: Sequence[tuple[str, Mapping[str, str]]],
    categories: Sequence[str],
    primary_category: str,
    children: Sequence[str],
    picture_file: str,
) -> tuple[str, ...]:
    """One `Contact list` row. ``scalars`` maps verbatim element names to source text."""
    mail, im = split_emails(emails)
    cells: dict[str, str] = {name: scalars.get(_element(src), "") for name, src in _SCALAR_COLUMNS.items()}
    cells["Name"] = display_name(scalars)
    for n in range(MAX_EMAIL_COLUMNS):
        cells[f"Email {n + 1}"] = mail[n] if n < len(mail) else ""
    cells["More emails"] = "; ".join(mail[MAX_EMAIL_COLUMNS:])
    cells["IM"] = "; ".join(im)
    for kind, column in (("Business", "Work address"), ("Home", "Home address"), ("Other", "Other address")):
        cells[column] = address(scalars, kind)
    cells["Children"] = "; ".join(_unique(children))
    cells["Categories"] = "; ".join(_unique([primary_category, *categories]))
    cells["Notes"] = scalars.get(f"{_P}NotesPlain", "") or scalars.get(f"{_P}Notes", "")
    cells["Picture"] = picture_file.rsplit("/", 1)[-1]
    cells["Source ref"] = record_key
    return tuple(fit_cell(cells[name]) for name in VIEW_HEADER)
