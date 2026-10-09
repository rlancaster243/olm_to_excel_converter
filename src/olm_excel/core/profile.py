"""Structure-only profiler for OLM archives (W00 evidence, U01).

Produces a report of an archive's *shape* so adapters can be designed
without anyone reading its contents:

- member counts, sizes, compression ratios and types sniffed from first bytes;
- for XML members: element and attribute names as collapsed paths, value-kind
  counts, maximum sibling repetition, depth and namespaces.

Never included: text values, attribute values, excerpts. Member path
segments are redacted by default (account addresses and folder names can be
personal): a segment is kept only if it is a generic Outlook/OLM name, digits
are collapsed to ``#``, and anything else becomes a salted hash token. The salt
is random per run and never written out, so tokens are consistent inside one
report but cannot be reversed by hashing guessed addresses.

Run it on the machine that holds the archive and review the report before
sharing it.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from olm_excel import __version__
from olm_excel.core.errors import ConversionError
from olm_excel.core.sniff import SNIFF_BYTES as _SNIFF_BYTES
from olm_excel.core.sniff import sniff_kind as _sniff
from olm_excel.core.walker import ValueKind, WalkLimits, iter_source_values
from olm_excel.core.xlsx_writer import EXCEL_CELL_MAX_UTF16, utf16_len

# Generic tokens that describe structure, not a person. Compared case-insensitively
# after digits are collapsed to "#". Extend only with names that cannot identify anyone.
GENERIC_TOKENS = frozenset(
    {
        "accounts", "account", "local", "address", "book", "contacts", "contact", "calendar",
        "calendars", "tasks", "task", "notes", "note", "messages", "message", "mail", "inbox",
        "sent", "items", "deleted", "drafts", "draft", "junk", "email", "outbox", "archive",
        "attachments", "attachment", "categories", "category", "signatures", "signature",
        "groups", "group", "folders", "folder", "com", "microsoft", "outlook", "olm", "xml",
        "plist", "eml", "ics", "vcf", "data", "metadata", "manifest", "index", "#",
    }
)
_TOKEN_SPLIT = re.compile(r"[^a-z#]+")
_INDEX = re.compile(r"\[(\d+)\]")
_ID_LIKE = re.compile(r"[0-9A-Fa-f-]{8,}")  # hex IDs and GUIDs

# Members larger than this, or expanding more than MAX_RATIO, are listed but not parsed.
MAX_PARSE_BYTES = 2 * 1024**3
MAX_RATIO = 200


@dataclass
class _PathStats:
    elements: int = 0
    text: int = 0
    empty: int = 0
    mixed_text: int = 0
    over_cell_cap: int = 0
    max_index: int = 1
    attributes: Counter[str] = field(default_factory=Counter)


@dataclass
class _GroupStats:
    members: int = 0
    bytes_uncompressed: int = 0
    bytes_compressed: int = 0
    max_ratio: float = 0.0
    types: Counter[str] = field(default_factory=Counter)
    encrypted: int = 0
    skipped: Counter[str] = field(default_factory=Counter)
    xml_parsed: int = 0
    xml_errors: Counter[str] = field(default_factory=Counter)
    source_values: int = 0
    roots: Counter[str] = field(default_factory=Counter)
    namespaces: set[str] = field(default_factory=set)
    max_depth: int = 0
    paths: dict[str, _PathStats] = field(default_factory=lambda: defaultdict(_PathStats))


class SegmentRedactor:
    """Map archive path segments to non-identifying forms, consistently per run."""

    def __init__(self, reveal: bool = False, salt: bytes | None = None) -> None:
        self._reveal = reveal
        self._salt = salt if salt is not None else secrets.token_bytes(16)

    def segment(self, seg: str, *, is_file: bool = False) -> str:
        if self._reveal:
            return seg
        collapsed = re.sub(r"\d+", "#", seg)
        tokens = [t for t in _TOKEN_SPLIT.split(collapsed.lower()) if t]
        if tokens and all(t in GENERIC_TOKENS for t in tokens):
            return collapsed
        suffix = Path(seg).suffix.lower()
        keep_suffix = suffix if suffix[1:] in GENERIC_TOKENS else ""
        if _ID_LIKE.fullmatch(Path(seg).stem):
            return f"<id>{keep_suffix}"
        if is_file:
            # File names need no identity for structure, and per-file hashes would
            # give every message or attachment its own group.
            return f"~file{keep_suffix}"
        digest = hashlib.blake2s(seg.encode("utf-8", "surrogatepass"), key=self._salt, digest_size=3).hexdigest()
        return f"~{digest}"

    def path(self, member_path: str) -> str:
        segments = member_path.split("/")
        return "/".join(self.segment(s, is_file=i == len(segments) - 1) for i, s in enumerate(segments))


def _collapse(element_path: str) -> tuple[str, int, int]:
    """Drop positional indexes. Returns (collapsed path, last index, depth)."""
    indexes = _INDEX.findall(element_path)
    return _INDEX.sub("", element_path), int(indexes[-1]) if indexes else 1, len(indexes)


def _prefixes(element_path: str) -> list[str]:
    """'/a[1]/b[2]/c[1]' -> ['/a[1]', '/a[1]/b[2]', '/a[1]/b[2]/c[1]']."""
    ends = [m.end() for m in _INDEX.finditer(element_path)]
    return [element_path[:end] for end in ends]


def _namespaces(tag_path: str) -> set[str]:
    return set(re.findall(r"\{([^}]*)\}", tag_path))


def profile_archive(
    path: Path,
    *,
    reveal_names: bool = False,
    progress: Callable[[int, int], None] | None = None,
    limits: WalkLimits = WalkLimits(),
) -> dict[str, Any]:
    """Return a structure-only profile of the archive at ``path`` (read-only)."""
    path = Path(path)
    redact = SegmentRedactor(reveal=reveal_names)
    report: dict[str, Any] = {
        "tool": f"olm-excel {__version__} profile",
        "contains_values": False,
        "names_redacted": not reveal_names,
        "input": {"bytes": path.stat().st_size},
    }
    with path.open("rb") as fh:
        report["input"]["sha256"] = hashlib.file_digest(fh, "sha256").hexdigest()
        fh.seek(0)
        report["input"]["container"] = _sniff(fh.read(_SNIFF_BYTES))
    if not zipfile.is_zipfile(path):
        report["error"] = "INPUT_INVALID: not a ZIP container"
        return report

    groups: dict[str, _GroupStats] = defaultdict(_GroupStats)
    unsafe_names = 0
    with zipfile.ZipFile(path) as archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        report["input"]["members"] = len(infos)
        for n, info in enumerate(infos, start=1):
            if progress:
                progress(n, len(infos))
            name = info.filename
            if name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/"):
                unsafe_names += 1
            group = groups[redact.path(name)]
            group.members += 1
            group.bytes_uncompressed += info.file_size
            group.bytes_compressed += info.compress_size
            ratio = info.file_size / info.compress_size if info.compress_size else 0.0
            group.max_ratio = max(group.max_ratio, ratio)
            if info.flag_bits & 0x1:
                group.encrypted += 1
                group.types["encrypted"] += 1
                continue
            if info.file_size > MAX_PARSE_BYTES or ratio > MAX_RATIO:
                group.skipped["size_or_ratio_limit"] += 1
                continue
            with archive.open(info) as member:
                kind = _sniff(member.read(_SNIFF_BYTES))
            group.types[kind] += 1
            if kind == "xml":
                _profile_xml(archive, info, group, limits)

    report["unsafe_member_names"] = unsafe_names
    report["member_groups"] = [_group_report(pattern, g) for pattern, g in sorted(groups.items())]
    report["totals"] = {
        "member_groups": len(groups),
        "xml_members_parsed": sum(g.xml_parsed for g in groups.values()),
        "source_values": sum(g.source_values for g in groups.values()),
    }
    return report


def _profile_xml(archive: zipfile.ZipFile, info: zipfile.ZipInfo, group: _GroupStats, limits: WalkLimits) -> None:
    # Values arrive in document order, so all values of one element instance are
    # seen before the next instance with the same collapsed path: remembering the
    # last instance per collapsed path is enough, and is bounded by schema size.
    last_instance: dict[str, str] = {}
    root_seen = False
    try:
        with archive.open(info) as member:
            for value in iter_source_values(member, limits):
                group.source_values += 1
                collapsed, _, depth = _collapse(value.element_path)
                if not root_seen:
                    group.roots["/" + collapsed.split("/")[1]] += 1
                    root_seen = True
                group.max_depth = max(group.max_depth, depth)
                # Count element instances for the value's element and every ancestor,
                # so containers that hold no values themselves (e.g. one contact) show up.
                for prefix in _prefixes(value.element_path):
                    prefix_collapsed, prefix_index, _ = _collapse(prefix)
                    if last_instance.get(prefix_collapsed) != prefix:
                        last_instance[prefix_collapsed] = prefix
                        ancestor = group.paths[prefix_collapsed]
                        ancestor.elements += 1
                        ancestor.max_index = max(ancestor.max_index, prefix_index)
                        group.namespaces |= _namespaces(prefix_collapsed)
                stats = group.paths[collapsed]
                if value.value_kind is ValueKind.ATTRIBUTE:
                    stats.attributes[value.attribute] += 1
                    group.namespaces |= _namespaces(value.attribute)
                elif value.value_kind is ValueKind.EMPTY:
                    stats.empty += 1
                else:
                    stats.text += 1
                    if value.text_position:
                        stats.mixed_text += 1
                if len(value.value) > EXCEL_CELL_MAX_UTF16 // 2 and utf16_len(value.value) > EXCEL_CELL_MAX_UTF16:
                    stats.over_cell_cap += 1
        group.xml_parsed += 1
    except ConversionError as exc:
        group.xml_errors[exc.code.value] += 1


def _group_report(pattern: str, g: _GroupStats) -> dict[str, Any]:
    out: dict[str, Any] = {
        "member_pattern": pattern,
        "members": g.members,
        "bytes_uncompressed": g.bytes_uncompressed,
        "bytes_compressed": g.bytes_compressed,
        "max_compression_ratio": round(g.max_ratio, 1),
        "types": dict(g.types),
    }
    for key, value in (("encrypted", g.encrypted), ("skipped", dict(g.skipped)), ("xml_errors", dict(g.xml_errors))):
        if value:
            out[key] = value
    if g.xml_parsed or g.xml_errors:
        out["xml"] = {
            "members_parsed": g.xml_parsed,
            "source_values": g.source_values,
            "roots": dict(g.roots),
            "namespaces": sorted(g.namespaces),
            "max_depth": g.max_depth,
            "paths": {
                p: {
                    k: v
                    for k, v in {
                        "elements": s.elements,
                        "text_values": s.text,
                        "empty_values": s.empty,
                        "mixed_text_values": s.mixed_text,
                        "values_over_cell_cap": s.over_cell_cap,
                        "max_sibling_index": s.max_index,
                        "attributes": dict(s.attributes),
                    }.items()
                    if v
                }
                for p, s in sorted(g.paths.items())
            },
        }
    return out
