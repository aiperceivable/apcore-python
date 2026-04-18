"""Sensitive field redaction utility (Algorithm A13)."""

from __future__ import annotations

import copy
from typing import Any

REDACTED_VALUE: str = "***REDACTED***"


def redact_sensitive(data: dict[str, Any], schema_dict: dict[str, Any]) -> dict[str, Any]:
    """Redact fields marked with x-sensitive in the schema.

    Implements Algorithm A13 from PROTOCOL_SPEC section 9.5.
    Returns a deep copy of data with sensitive values replaced by "***REDACTED***".
    Also redacts any keys starting with "_secret_" regardless of schema.

    Args:
        data: The data dict to redact.
        schema_dict: A JSON Schema dict that may contain "x-sensitive": true
            on individual properties.

    Returns:
        A new dict with sensitive values replaced. Original data is not modified.
    """
    redacted = copy.deepcopy(data)
    _redact_fields(redacted, schema_dict)
    _redact_secret_prefix(redacted)
    return redacted


def _redact_fields(data: dict[str, Any], schema_dict: dict[str, Any]) -> None:
    """In-place redaction based on schema x-sensitive markers."""
    properties = schema_dict.get("properties")
    if not properties:
        return

    for field_name, field_schema in properties.items():
        if field_name not in data:
            continue

        value = data[field_name]

        # x-sensitive: true on this property
        if field_schema.get("x-sensitive") is True:
            if value is not None:
                data[field_name] = REDACTED_VALUE
            continue

        # Nested object: recurse
        if field_schema.get("type") == "object" and "properties" in field_schema and isinstance(value, dict):
            _redact_fields(value, field_schema)
            continue

        # Array: redact items
        if field_schema.get("type") == "array" and "items" in field_schema and isinstance(value, list):
            items_schema = field_schema["items"]
            if items_schema.get("x-sensitive") is True:
                for i, item in enumerate(value):
                    if item is not None:
                        value[i] = REDACTED_VALUE
            elif items_schema.get("type") == "object" and "properties" in items_schema:
                for item in value:
                    if isinstance(item, dict):
                        _redact_fields(item, items_schema)


def _redact_secret_prefix(data: dict[str, Any]) -> None:
    """In-place redaction of keys starting with _secret_ at any depth.

    Recurses into dict children and into list items, handling the common
    ``list[dict]`` shape where secret-prefixed keys can otherwise slip through.
    """
    for key in data:
        value = data[key]
        if key.startswith("_secret_") and value is not None:
            data[key] = REDACTED_VALUE
        elif isinstance(value, dict):
            _redact_secret_prefix(value)
        elif isinstance(value, list):
            _redact_secret_prefix_in_list(value)


def _redact_secret_prefix_in_list(items: list[Any]) -> None:
    """Traverse a list, redacting dict children and recursing into nested lists."""
    for item in items:
        if isinstance(item, dict):
            _redact_secret_prefix(item)
        elif isinstance(item, list):
            _redact_secret_prefix_in_list(item)
