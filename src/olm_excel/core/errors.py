"""Stable failure codes (06 failure taxonomy).

Error messages carry codes, scope and positions only. They must never
include source values, which may be personal data (N05).
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    INPUT_INVALID = "INPUT_INVALID"
    ARCHIVE_UNSAFE = "ARCHIVE_UNSAFE"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    FORMAT_UNKNOWN = "FORMAT_UNKNOWN"
    AMBIGUOUS_ADAPTER = "AMBIGUOUS_ADAPTER"
    RECORD_PARSE_ERROR = "RECORD_PARSE_ERROR"
    FIELD_LOSS_RISK = "FIELD_LOSS_RISK"
    EXCEL_LIMIT = "EXCEL_LIMIT"
    RAW_EXTRACT_LIMIT = "RAW_EXTRACT_LIMIT"
    RAW_EXTRACT_DISABLED = "RAW_EXTRACT_DISABLED"
    OUTPUT_IO = "OUTPUT_IO"
    CANCELLED = "CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ConversionError(Exception):
    """A classified failure with a stable code and a safe message."""

    def __init__(self, code: ErrorCode, message: str, *, scope: str = "member") -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.scope = scope
