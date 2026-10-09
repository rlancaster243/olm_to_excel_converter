"""Safe archive intake (W02).

Contract: docs/fidelity/06-THREATS-AND-FAILURES.md (ZIP slip, ZIP bombs) and
03 "Archive guard". The guard validates the whole central directory before
any member is read, never extracts to disk, and hands out members only as
bounded streams.

Rejected before any parsing (ARCHIVE_UNSAFE): absolute or drive paths, ``..``
segments, NUL or control characters, over-long names, duplicate names, and
symbolic links. Resource limits (RESOURCE_LIMIT): entry count, total and
per-member uncompressed size, per-member compression ratio.

The default limits are placeholders, not a calibrated ZIP-bomb defense (09
Runbook 7). They are far above the one real export seen (74 MB largest member,
stored uncompressed): 2 GiB per member is about 28 times that member, so they
bound the work a hostile archive can cause rather than catch every one; the
compression ratio cap is the main early guard. Rejecting a legitimate outlier
is still the cheaper error, and the operator can allow one explicitly
(``--max-member-gib``, ``--max-ratio``). There is no wall-clock parse limit yet
(N03, W08). Nested archives are inventoried by type and never opened.
"""

from __future__ import annotations

import hashlib
import re
import stat
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

from olm_excel.core.errors import ConversionError, ErrorCode
from olm_excel.core.sniff import SNIFF_BYTES, sniff_kind

_READ_CAP = 1 << 20  # one read never returns more than 1 MiB
_DRIVE = re.compile(r"^[A-Za-z]:")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_entries: int = 1_000_000
    max_total_uncompressed: int = 64 * 1024**3
    max_member_uncompressed: int = 2 * 1024**3
    max_ratio: float = 100.0  # per member; stored members have ratio 1
    max_path_length: int = 1024


@dataclass(frozen=True, slots=True)
class MemberInfo:
    ordinal: int  # 1-based position among file members, in archive order
    path: str
    size: int
    compressed: int
    encrypted: bool
    _info: zipfile.ZipInfo

    @property
    def ratio(self) -> float:
        return self.size / self.compressed if self.compressed else 0.0


@dataclass(frozen=True, slots=True)
class ArchiveInventory:
    members: tuple[MemberInfo, ...]
    sha256: str
    size_bytes: int

    @property
    def total_uncompressed(self) -> int:
        return sum(m.size for m in self.members)


def _unsafe(message: str) -> ConversionError:
    return ConversionError(ErrorCode.ARCHIVE_UNSAFE, message, scope="archive")


def _limit(message: str) -> ConversionError:
    return ConversionError(ErrorCode.RESOURCE_LIMIT, message, scope="archive")


def _check_name(name: str, limits: ArchiveLimits) -> None:
    if len(name) > limits.max_path_length:
        raise _unsafe("member path is too long")
    if _CONTROL.search(name):
        raise _unsafe("member path contains control characters")
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or _DRIVE.match(normalized):
        raise _unsafe("member path is absolute")
    if ".." in normalized.split("/"):
        raise _unsafe("member path contains a parent directory segment")


class _MemberStream:
    """Bounded, read-only view of one member that turns decoder failures into classified errors."""

    def __init__(self, raw: BinaryIO, limit: int) -> None:
        self._raw = raw
        self._left = limit

    def read(self, n: int = -1) -> bytes:
        """Read at most 1 MiB. A short read is legal; an unbounded read of a larger member is refused.

        Silently truncating ``read()`` would hand a caller that expects everything a wrong answer,
        so it raises instead: loop with a size to consume a large member (ADR-004).
        """
        unbounded = n is None or n < 0
        if unbounded:
            n = min(_READ_CAP + 1, self._left + 1)
        else:
            n = min(n, _READ_CAP, self._left + 1)  # +1 detects a member that expands past its declared size
        try:
            data = self._raw.read(n)
        except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError, OSError) as exc:
            raise ConversionError(ErrorCode.INPUT_INVALID, f"member failed to decode: {type(exc).__name__}") from exc
        self._left -= len(data)
        if self._left < 0:
            raise _limit("member expanded beyond its declared size")
        if unbounded and len(data) > _READ_CAP:
            raise _limit("unbounded read of a large member; read it in chunks")
        return data

    def close(self) -> None:
        self._raw.close()

    def __enter__(self) -> _MemberStream:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()


class SafeArchive:
    """A validated, read-only OLM container. Use ``SafeArchive.open``."""

    def __init__(self, zf: zipfile.ZipFile, inventory: ArchiveInventory, limits: ArchiveLimits) -> None:
        self._zf = zf
        self.inventory = inventory
        self.limits = limits

    @classmethod
    def open(cls, path: Path, limits: ArchiveLimits = ArchiveLimits()) -> SafeArchive:
        path = Path(path)
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise ConversionError(ErrorCode.INPUT_INVALID, f"cannot read input: {type(exc).__name__}", scope="archive") from exc
        if not path.is_file() or size == 0:
            raise ConversionError(ErrorCode.INPUT_INVALID, "input is not a non-empty file", scope="archive")
        try:
            zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError, NotImplementedError) as exc:
            raise ConversionError(ErrorCode.INPUT_INVALID, "input is not a readable ZIP container", scope="archive") from exc
        try:
            members = cls._validate(zf, limits)
            with path.open("rb") as fh:
                digest = hashlib.file_digest(fh, "sha256").hexdigest()
        except BaseException:
            zf.close()
            raise
        return cls(zf, ArchiveInventory(tuple(members), digest, size), limits)

    @staticmethod
    def _validate(zf: zipfile.ZipFile, limits: ArchiveLimits) -> list[MemberInfo]:
        infos = zf.infolist()
        if len(infos) > limits.max_entries:
            raise _limit(f"archive has more than {limits.max_entries} entries")
        members: list[MemberInfo] = []
        seen: set[str] = set()
        total = 0
        for info in infos:
            name = info.filename
            _check_name(name, limits)
            if info.is_dir():
                continue
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise _unsafe("archive contains a symbolic link")
            key = name.replace("\\", "/")
            if key in seen:
                raise _unsafe("archive contains duplicate member names")
            seen.add(key)
            if info.file_size > limits.max_member_uncompressed:
                raise _limit("a member exceeds the per-member size limit")
            if info.file_size and not info.compress_size:
                raise _limit("a member declares data but no compressed bytes")
            if info.compress_size and info.file_size / info.compress_size > limits.max_ratio:
                raise _limit("a member exceeds the compression ratio limit")
            total += info.file_size
            if total > limits.max_total_uncompressed:
                raise _limit("archive exceeds the total uncompressed size limit")
            members.append(
                MemberInfo(len(members) + 1, name, info.file_size, info.compress_size, bool(info.flag_bits & 0x1), info)
            )
        return members

    def open_member(self, member: MemberInfo) -> _MemberStream:
        """Open one member as a bounded stream. Encrypted members are refused (U06)."""
        if member.encrypted:
            raise ConversionError(ErrorCode.FORMAT_UNKNOWN, "member is encrypted", scope="member")
        try:
            raw = self._zf.open(member._info)
        except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError) as exc:
            raise ConversionError(ErrorCode.FORMAT_UNKNOWN, f"member cannot be opened: {type(exc).__name__}") from exc
        return _MemberStream(raw, member.size)

    def sniff(self, member: MemberInfo) -> str:
        """Classify a member from its first bytes; encrypted members are reported as such."""
        if member.encrypted:
            return "encrypted"
        try:
            with self.open_member(member) as stream:
                return sniff_kind(stream.read(SNIFF_BYTES))
        except ConversionError:
            return "unreadable"

    def close(self) -> None:
        self._zf.close()

    def __enter__(self) -> SafeArchive:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()


__all__ = ["ArchiveInventory", "ArchiveLimits", "MemberInfo", "SafeArchive"]
