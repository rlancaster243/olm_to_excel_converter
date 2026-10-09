"""Core source-value walker and raw extractor (W04).

Contract: docs/fidelity/04-CONTRACTS-AND-DATA.md, "Source values" and
"Raw extract contract". Adapters read XML members through this walker;
it counts every source value independently of any adapter.
"""

from __future__ import annotations

from typing import BinaryIO


def count_source_values(member: BinaryIO) -> int:
    """Return the number of source values in one XML member stream.

    Must stream with bounded memory (ADR-004) using the hardened parser.
    """
    raise NotImplementedError("W04: source-value walker")
