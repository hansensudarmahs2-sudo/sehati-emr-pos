"""
JSON writer helper untuk Owner Raw Data Export module.

Pattern: convert list of dict → bytes JSON (UTF-8, pretty-printed dengan indent).
Pakai default=str untuk auto-convert datetime/Decimal/date ke string.
"""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable


def _json_default(obj: Any) -> str:
    """Default serializer untuk type yang tidak native JSON-serializable."""
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, date):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, Decimal):
        return str(obj)
    return str(obj)


def dict_list_to_json_bytes(
    items: Iterable[dict],
    pretty: bool = True,
) -> bytes:
    """
    Convert list of dict ke JSON bytes.

    Args:
        items: iterable of dict
        pretty: True = indent=2 (human readable), False = compact (smaller).

    Returns:
        UTF-8 encoded JSON bytes. Format: top-level array of objects.
    """
    items_list = list(items) if not isinstance(items, list) else items

    indent = 2 if pretty else None
    text = json.dumps(
        items_list,
        ensure_ascii=False,
        indent=indent,
        default=_json_default,
    )
    return text.encode("utf-8")


__all__ = ["dict_list_to_json_bytes"]
