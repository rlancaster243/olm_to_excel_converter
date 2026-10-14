"""Phone fidelity audit: does what the workbook stores equal what the archive says, per phone value?

Aggregate only. The report never contains a phone value, a name or a path: counts, shape classes and
cell kinds. It exists to test one question with evidence: when phone numbers are garbled, is the
conversion doing it, or does it happen later (a number-inferring import, an edit in Excel)?

Three measurements:
1. SOURCE shape: how many source phone values have a shape that numeric inference would alter
   (leading plus, leading zero, more than 15 digits, exponent form, date-like), and how many start with a
   character Excel treats as a formula or number prefix (= + - @).
2. WORKBOOK fidelity, per key: for every source phone value, compare it with the cell in the `contacts`
   sheet and in the `Contact list` view (matched by record key): exact text, whitespace-only difference,
   truncation, different text, a number stored instead of text, a formula, or a missing cell.
3. EDIT SAFETY: how many text cells carry Excel's quote prefix. Without it, editing such a cell in Excel
   re-parses the text (a leading plus or zero is lost), even though the stored cell is exact.

The numeric-inference rules are a model of what a number-inferring consumer would do, not a claim about
any one program. Their definitions are in this module so the model can be read and challenged.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from olm_excel import __version__
from olm_excel.adapters import default_adapters
from olm_excel.adapters.base import split_path
from olm_excel.adapters.contacts import COLUMNS, SCALAR_ELEMENTS
from olm_excel.core.archive_guard import SafeArchive
from olm_excel.core.discovery import select_adapter, sniff_signature
from olm_excel.core.errors import ConversionError
from olm_excel.core.walker import ValueKind, iter_source_values
from olm_excel.core.xlsx_read import Cell, iter_rows, sheet_names

CONTACTS_ADAPTER = "contacts-olm-v1"
PHONE_ELEMENTS: tuple[str, ...] = tuple(e for e in SCALAR_ELEMENTS if any(k in COLUMNS[e] for k in ("Phone", "Fax", "Pager")))
PHONE_COLUMNS: tuple[str, ...] = tuple(COLUMNS[e] for e in PHONE_ELEMENTS)
# `Contact list` column -> `contacts` column. Written independently of the view code on purpose.
VIEW_PHONE_COLUMNS = {
    "Mobile": "CellPhone", "Work phone": "BusinessPhone", "Work phone 2": "BusinessPhone2",
    "Home phone": "HomePhone", "Home phone 2": "HomePhone2", "Main phone": "MainPhone",
    "Other phone": "OtherPhone", "Assistant phone": "AssistantPhone", "Work fax": "BusinessFax",
    "Home fax": "HomeFax", "Pager": "Pager", "Radio phone": "RadioPhone",
}

_PLAIN_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?")
_EXPONENT = re.compile(r"[+-]?\d+(?:\.\d+)?[eE][+-]?\d+")
_DATE_LIKE = re.compile(r"(\d{1,2})[-/](\d{1,2})(?:[-/]\d{2,4})?")
_EXTENSION = re.compile(r"(?i)(?:\bext\.?|\bx|#)\s*\d")
_SEPARATORS = re.compile(r"[ \-.()]")
_FORMULA_PREFIX = "=+-@"


def numeric_inference_cause(text: str) -> str | None:
    """Why a number-inferring consumer would alter this text, or None if it would keep it.

    Model: after trimming, a value that parses as a plain number, an exponent form or a short date is
    converted, and the converted form loses what the text carried (the plus sign, leading zeros, digits
    beyond 15, the original spelling). Anything with spaces, brackets, letters or several separators stays text.
    """
    t = text.strip()
    if not t:
        return None
    if _EXPONENT.fullmatch(t):
        return "exponent_form"
    if _PLAIN_NUMBER.fullmatch(t):
        if t.startswith("+"):
            return "leading_plus"
        if re.match(r"-?0\d", t):
            return "leading_zero"
        if sum(ch.isdigit() for ch in t) > 15:
            return "over_15_digits"
        return None
    m = _DATE_LIKE.fullmatch(t)
    if m and int(m.group(1)) <= 31 and int(m.group(2)) <= 31:
        return "date_like"
    return None


def shape_flags(text: str) -> list[str]:
    """Non-exclusive shape classes of one source value. Never returns the value itself."""
    t = text.strip()
    flags: list[str] = []
    if not t:
        return ["empty_or_blank"]
    if text != t:
        flags.append("outer_whitespace")
    if t.startswith("+"):
        flags.append("plus_prefix")
    if t[0] in _FORMULA_PREFIX:
        flags.append("formula_prefix")
    if t.isdigit():
        flags.append("digits_only")
    if re.match(r"\+?0\d", t):
        flags.append("leading_zero")
    if sum(ch.isdigit() for ch in t) > 15:
        flags.append("over_15_digits")
    if _SEPARATORS.search(t):
        flags.append("has_separators")
    if _EXTENSION.search(t):
        flags.append("has_extension")
    if any(ch.isalpha() for ch in _EXTENSION.sub("", t)):
        flags.append("has_letters")
    if re.search(r"[;/,]", t):
        flags.append("several_numbers_or_list")
    if not t.isascii():
        flags.append("non_ascii")
    return flags


@dataclass
class _Source:
    values: dict[tuple[str, str], str] = field(default_factory=dict)  # (record_key, contacts column) -> text
    records: int = 0
    members: int = 0
    unmapped_phone_values: int = 0  # phone-named elements the converter would not place in a column
    by_field: Counter = field(default_factory=Counter)
    shapes: Counter = field(default_factory=Counter)
    causes: Counter = field(default_factory=Counter)
    field_alters: Counter = field(default_factory=Counter)  # column -> values numeric inference would alter
    field_formula_prefix: Counter = field(default_factory=Counter)  # column -> values starting with = + - @


def _read_source(archive_path: Path, progress: Callable[[int, int], None] | None) -> tuple[_Source, str, int]:
    src = _Source()
    adapters = default_adapters()
    with SafeArchive.open(archive_path) as archive:
        inv = archive.inventory
        archive_id = inv.sha256[:12]
        for n, member in enumerate(inv.members, start=1):
            if progress:
                progress(n, len(inv.members))
            if archive.sniff(member) not in ("xml", "xml-utf16"):
                continue
            try:
                with archive.open_member(member) as stream:
                    adapter, _ = select_adapter(sniff_signature(stream), adapters)
            except ConversionError:
                continue
            if adapter is None or adapter.adapter_id != CONTACTS_ADAPTER:
                continue
            src.members += 1
            _read_member(archive, member, archive_id, src)
    return src, inv.sha256, inv.size_bytes


def _read_member(archive: SafeArchive, member, archive_id: str, src: _Source) -> None:
    current = 0
    with archive.open_member(member) as stream:
        for value in iter_source_values(stream):
            segs = split_path(value.element_path)
            if segs is None or len(segs) < 2 or segs[0] != ("contacts", 1) or segs[1][0] != "contact":
                continue
            if segs[1][1] != current:
                current = segs[1][1]
                src.records += 1
            if len(segs) != 3 or segs[2][0] not in PHONE_ELEMENTS or value.value_kind is ValueKind.ATTRIBUTE:
                continue
            column = COLUMNS[segs[2][0]]
            if segs[2][1] != 1 or value.value_kind is not ValueKind.TEXT or value.text_position != 0:
                src.unmapped_phone_values += 1
                continue
            src.values[(f"{archive_id}/{member.ordinal}/{current}", column)] = value.value
            src.by_field[column] += 1
            flags = shape_flags(value.value)
            for flag in flags:
                src.shapes[flag] += 1
            if "formula_prefix" in flags:
                src.field_formula_prefix[column] += 1
            cause = numeric_inference_cause(value.value)
            if cause:
                src.causes[cause] += 1
                src.field_alters[column] += 1


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 2) if whole else 0.0


def _compare(workbook: Path, base: str, key_header: str, column_map: dict[str, str], src: _Source) -> dict[str, Any]:
    names = [n for n in sheet_names(workbook) if n == base or re.fullmatch(re.escape(base) + r"_\d{4}", n)]
    result: dict[str, Any] = {"sheets_read": len(names)}
    if not names:
        result["sheet_missing"] = True
        return result
    cells: Counter = Counter()
    by_field: dict[str, Counter] = {}
    not_exact_by_shape: Counter = Counter()
    altered_by_cause: Counter = Counter()
    quote: Counter = Counter()
    seen: set[str] = set()
    for name in names:
        columns: dict[int, str] = {}
        key_idx = -1
        for r, row in enumerate(iter_rows(workbook, name)):
            if r == 0:
                headers = {i: c.text for i, c in row.items()}
                key_idx = next((i for i, h in headers.items() if h == key_header), -1)
                columns = {i: column_map[h] for i, h in headers.items() if h in column_map}
                continue
            key_cell = row.get(key_idx)
            if key_cell is None:
                continue
            key = key_cell.text
            seen.add(key)
            for idx, column in columns.items():
                _judge(src.values.get((key, column)), row.get(idx), column, cells, by_field, not_exact_by_shape, altered_by_cause, quote)
    source_keys = {k for k, _ in src.values}
    missing_records = source_keys - seen
    missing_values = sum(1 for (k, _c) in src.values if k in missing_records)
    if missing_values:
        cells["missing_row"] += missing_values
    result.update(
        records_found=len(seen & source_keys), source_records_not_found=len(missing_records),
        cells=dict(sorted(cells.items())),
        not_exact_by_field={f: dict(sorted(c.items())) for f, c in sorted(by_field.items())},
        not_exact_by_source_shape=dict(sorted(not_exact_by_shape.items())),
        number_cells_altered_by_cause=dict(sorted(altered_by_cause.items())),
        quote_prefix=dict(sorted(quote.items())),
    )
    return result


def _judge(s: str | None, cell: Cell | None, column: str, cells: Counter, by_field: dict[str, Counter],
           shapes: Counter, causes: Counter, quote: Counter) -> None:
    if s is None:
        if cell is not None and cell.text.strip():
            cells["extra_cell_without_source"] += 1
        return
    if cell is None:
        outcome = "missing_cell"
    elif cell.kind == "text":
        if cell.text == s:
            outcome = "exact"
        elif cell.text.strip() == s.strip():
            outcome = "whitespace_only"
        elif s.startswith(cell.text):
            outcome = "truncated"
        else:
            outcome = "different"
        key = "text_with_quote_prefix" if cell.quote_prefix else "text_without_quote_prefix"
        quote[key] += 1
        if s.strip()[:1] in tuple(_FORMULA_PREFIX) and not cell.quote_prefix:
            quote["formula_prefix_text_without_quote_prefix"] += 1
    elif cell.kind == "number":
        outcome = "number_same_digits" if cell.text == s.strip() else "number_altered"
        if outcome == "number_altered":
            causes[numeric_inference_cause(s) or "other"] += 1
    elif cell.kind == "formula":
        outcome = "formula"
    else:
        outcome = "bool_or_error"
    cells[outcome] += 1
    if outcome != "exact":
        by_field.setdefault(column, Counter())[outcome] += 1
        for flag in shape_flags(s):
            shapes[flag] += 1


def audit_phones(archive_path: Path, workbook_path: Path | None = None, *, progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    """Return the aggregate-only audit report. ``workbook_path`` is optional: without it only the source is profiled."""
    src, sha, size = _read_source(Path(archive_path), progress)
    total = len(src.values)
    report: dict[str, Any] = {
        "tool": f"olm-excel {__version__} audit-phones",
        "contains_values": False,
        "input": {"bytes": size, "sha256": sha},
        "source": {
            "contacts_members": src.members,
            "records": src.records,
            "phone_values": total,
            "phone_values_not_placed_in_a_column": src.unmapped_phone_values,
            "by_field": dict(sorted(src.by_field.items())),
            "shape_counts": dict(sorted(src.shapes.items())),
            "numeric_inference": {
                "would_alter": sum(src.causes.values()),
                "would_alter_pct": _pct(sum(src.causes.values()), total),
                "by_cause": dict(sorted(src.causes.items())),
            },
            "formula_prefix_pct": _pct(src.shapes["formula_prefix"], total),
            "risk_by_field": {
                col: {
                    "values": n,
                    "would_alter": src.field_alters[col],
                    "would_alter_pct": _pct(src.field_alters[col], n),
                    "formula_prefix": src.field_formula_prefix[col],
                    "formula_prefix_pct": _pct(src.field_formula_prefix[col], n),
                }
                for col, n in sorted(src.by_field.items())
            },
        },
    }
    if workbook_path is not None:
        wb = Path(workbook_path)
        contacts = _compare(wb, "contacts", "record_key", {c: c for c in PHONE_COLUMNS}, src)
        view = _compare(wb, "Contact list", "Source ref", VIEW_PHONE_COLUMNS, src)
        for part in (contacts, view):
            exact = part.get("cells", {}).get("exact", 0)
            part["exact_pct_of_source_phone_values"] = _pct(exact, total)
        report["workbook"] = {"contacts": contacts, "contact_list": view}
    return report
