"""Versioned OLM adapters (doc 04 adapter contract)."""

from __future__ import annotations

from olm_excel.adapters.base import Adapter
from olm_excel.adapters.categories import CategoriesAdapter
from olm_excel.adapters.contacts import DEFAULT_MAX_PICTURE_BYTES, ContactsAdapter, PictureSink


def default_adapters(
    picture_sink: PictureSink | None = None, max_picture_bytes: int = DEFAULT_MAX_PICTURE_BYTES
) -> list[Adapter]:
    """Fresh adapter instances for one conversion run (they hold per-run sheets)."""
    return [ContactsAdapter(picture_sink, max_picture_bytes), CategoriesAdapter()]
