"""Member type sniffing from the first bytes. File names and extensions are never trusted."""

from __future__ import annotations

SNIFF_BYTES = 64


def sniff_kind(head: bytes) -> str:
    """Classify a member from its first bytes: xml, xml-utf16, zip, binary-plist, empty or binary."""
    stripped = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith(b"<"):
        return "xml"
    if head.startswith((b"\xff\xfe<", b"\xfe\xff\x00<")):
        return "xml-utf16"
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    if head.startswith(b"bplist"):
        return "binary-plist"
    if not head:
        return "empty"
    return "binary"
