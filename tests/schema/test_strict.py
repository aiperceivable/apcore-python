"""Tests for strict mode conversion functions."""

from __future__ import annotations

import copy
from typing import Any

from apcore.schema.strict import (
    _apply_llm_descriptions,
    _strip_extensions,
    to_strict_schema,
)


# === to_strict_schema() ===


class TestToStrictSchema:
    def test_optional_becomes_required_nullable(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }
        result = to_strict_schema(schema)
        assert "name" in result["required"]
        assert result["properties"]["name"]["type"] == ["string", "null"]

    def test_x_fields_stripped(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "x-llm-description": "Full name",
                    "x-examples": ["Alice"],
                },
            },
            "required": ["name"],
        }
        result = to_strict_schema(schema)
        assert "x-llm-description" not in result["properties"]["name"]
        assert "x-examples" not in result["properties"]["name"]

    def test_default_values_removed(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {"count": {"type": "integer", "default": 42}},
            "required": ["count"],
        }
        result = to_strict_schema(schema)
        assert "default" not in result["properties"]["count"]

    def test_additional_properties_false(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        result = to_strict_schema(schema)
        assert result["additionalProperties"] is False

    def test_already_required_stays_unchanged(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        result = to_strict_schema(schema)
        assert result["properties"]["name"]["type"] == "string"

    def test_already_nullable_not_double_nullified(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {"name": {"type": ["string", "null"]}},
        }
        result = to_strict_schema(schema)
        assert result["properties"]["name"]["type"] == ["string", "null"]

    def test_ref_field_wrapped_in_oneof(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {"address": {"$ref": "#/definitions/Address"}},
        }
        result = to_strict_schema(schema)
        prop = result["properties"]["address"]
        assert "oneOf" in prop
        assert {"$ref": "#/definitions/Address"} in prop["oneOf"]
        assert {"type": "null"} in prop["oneOf"]

    def test_nested_objects_recursively_converted(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "properties": {"retry": {"type": "integer"}},
                },
            },
            "required": ["config"],
        }
        result = to_strict_schema(schema)
        config = result["properties"]["config"]
        assert config["additionalProperties"] is False
        assert "retry" in config["required"]

    def test_array_items_recursively_converted(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"qty": {"type": "integer"}},
                    },
                },
            },
            "required": ["items"],
        }
        result = to_strict_schema(schema)
        item_schema = result["properties"]["items"]["items"]
        assert item_schema["additionalProperties"] is False
        assert "qty" in item_schema["required"]

    def test_oneof_sub_schemas_recursively_converted(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "value": {
                    "oneOf": [
                        {"type": "object", "properties": {"a": {"type": "string"}}},
                        {"type": "string"},
                    ]
                },
            },
            "required": ["value"],
        }
        result = to_strict_schema(schema)
        obj_branch = result["properties"]["value"]["oneOf"][0]
        assert obj_branch["additionalProperties"] is False
        assert "a" in obj_branch["required"]

    def test_original_unmodified(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {"name": {"type": "string", "x-foo": True}},
        }
        original = copy.deepcopy(schema)
        to_strict_schema(schema)
        assert schema == original

    def test_empty_schema(self) -> None:
        result = to_strict_schema({})
        assert result == {}

    def test_required_sorted(self) -> None:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "zebra": {"type": "string"},
                "apple": {"type": "string"},
                "mango": {"type": "string"},
            },
        }
        result = to_strict_schema(schema)
        assert result["required"] == ["apple", "mango", "zebra"]


# === _apply_llm_descriptions() ===


class TestApplyLlmDescriptions:
    def test_replaces_description(self) -> None:
        node: dict[str, Any] = {
            "description": "short",
            "x-llm-description": "long detailed",
        }
        _apply_llm_descriptions(node)
        assert node["description"] == "long detailed"
        assert "x-llm-description" in node  # stripping happens separately

    def test_preserves_description_without_llm(self) -> None:
        node: dict[str, Any] = {"description": "short"}
        _apply_llm_descriptions(node)
        assert node["description"] == "short"

    def test_recursive_into_properties(self) -> None:
        node: dict[str, Any] = {
            "type": "object",
            "properties": {
                "a": {"description": "old", "x-llm-description": "new"},
            },
        }
        _apply_llm_descriptions(node)
        assert node["properties"]["a"]["description"] == "new"

    def test_no_llm_description_unchanged(self) -> None:
        node: dict[str, Any] = {"description": "keep me", "type": "string"}
        _apply_llm_descriptions(node)
        assert node["description"] == "keep me"


# === _strip_extensions() ===


class TestStripExtensions:
    def test_x_keys_removed(self) -> None:
        node: dict[str, Any] = {"x-foo": 1, "x-bar": 2, "type": "string"}
        _strip_extensions(node)
        assert node == {"type": "string"}

    def test_default_keys_removed(self) -> None:
        node: dict[str, Any] = {"default": 42, "type": "integer"}
        _strip_extensions(node)
        assert node == {"type": "integer"}

    def test_recursive_into_nested(self) -> None:
        node: dict[str, Any] = {"properties": {"a": {"x-sensitive": True, "type": "string"}}}
        _strip_extensions(node)
        assert node == {"properties": {"a": {"type": "string"}}}

    def test_non_x_keys_preserved(self) -> None:
        node: dict[str, Any] = {
            "type": "object",
            "description": "test",
            "properties": {},
        }
        _strip_extensions(node)
        assert "type" in node
        assert "description" in node
        assert "properties" in node

    def test_strip_defaults_false_preserves_defaults(self) -> None:
        """strip_defaults=False keeps default keys while still removing x-* keys."""
        node: dict[str, Any] = {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "default": 10, "x-sensitive": True},
                "name": {"type": "string", "x-llm-description": "Full name"},
            },
        }
        _strip_extensions(node, strip_defaults=False)
        # x-* keys removed
        assert "x-sensitive" not in node["properties"]["count"]
        assert "x-llm-description" not in node["properties"]["name"]
        # default preserved
        assert node["properties"]["count"]["default"] == 10

    def test_strip_defaults_true_removes_defaults(self) -> None:
        """strip_defaults=True (default) removes both x-* and default keys."""
        node: dict[str, Any] = {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "default": 10, "x-sensitive": True},
            },
        }
        _strip_extensions(node, strip_defaults=True)
        assert "x-sensitive" not in node["properties"]["count"]
        assert "default" not in node["properties"]["count"]

    def test_strip_defaults_false_recursive(self) -> None:
        """strip_defaults=False recursively preserves defaults in nested structures."""
        node: dict[str, Any] = {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "properties": {
                        "retry": {"type": "integer", "default": 3, "x-internal": True},
                    },
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string", "default": "untagged", "x-hint": "tag"},
                },
            },
        }
        _strip_extensions(node, strip_defaults=False)
        assert node["properties"]["config"]["properties"]["retry"]["default"] == 3
        assert "x-internal" not in node["properties"]["config"]["properties"]["retry"]
        assert node["properties"]["tags"]["items"]["default"] == "untagged"
        assert "x-hint" not in node["properties"]["tags"]["items"]
