"""Cross-language module ID normalization (Algorithm A02)."""

from __future__ import annotations

import re

__all__ = ["normalize_to_canonical_id"]

#: Language-specific separators used to split local IDs.
_SEPARATORS: dict[str, str] = {
    "python": ".",
    "rust": "::",
    "go": ".",
    "java": ".",
    "typescript": ".",
}

_SUPPORTED_LANGUAGES: frozenset[str] = frozenset(_SEPARATORS)

#: Regex for splitting PascalCase / camelCase into words.
#  Handles transitions like: "Http" | "JSON" | "Parser" | "v2".
_CASE_BOUNDARY = re.compile(
    r"""
    (?<=[a-z0-9])(?=[A-Z])     # lowercase/digit → uppercase  (e.g. "http|Json")
    | (?<=[A-Z])(?=[A-Z][a-z]) # uppercase run → start of word (e.g. "HTTP|Json")
    """,
    re.VERBOSE,
)

#: Canonical ID format from PROTOCOL_SPEC §2.7 EBNF grammar.
_CANONICAL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


def _to_snake_case(segment: str) -> str:
    """Convert a PascalCase, camelCase, or mixed-case segment to snake_case.

    Acronyms are treated as single words::

        "HttpJsonParser" → "http_json_parser"
        "HTMLParser"     → "html_parser"
        "getDBUrl"       → "get_db_url"
    """
    if not segment:
        return segment

    # If already snake_case (all lowercase + underscores), return as-is.
    if segment == segment.lower() and segment.isidentifier():
        return segment

    # Split at case boundaries, join with underscore, lowercase.
    words = _CASE_BOUNDARY.split(segment)
    return "_".join(w.lower() for w in words if w)


def normalize_to_canonical_id(local_id: str, language: str) -> str:
    """Convert a language-local module ID to Canonical ID format (Algorithm A02).

    Steps:
        1. Split by language-specific separator.
        2. Normalize each segment from PascalCase/camelCase to snake_case.
        3. Join with ``"."`` and validate against Canonical ID EBNF.

    Args:
        local_id: Language-local format ID (e.g. ``"executor::validator::DbParams"``).
        language: Source language (``"python"`` | ``"rust"`` | ``"go"`` | ``"java"`` | ``"typescript"``).

    Returns:
        Dot-separated snake_case Canonical ID.

    Raises:
        ValueError: If *language* is unsupported or the result is not a valid Canonical ID.
    """
    if not local_id:
        raise ValueError("local_id must be a non-empty string")

    if language not in _SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported language '{language}'. " f"Must be one of: {', '.join(sorted(_SUPPORTED_LANGUAGES))}"
        )

    separator = _SEPARATORS[language]
    segments = local_id.split(separator)

    normalized = [_to_snake_case(seg) for seg in segments]
    canonical_id = ".".join(normalized)

    if not _CANONICAL_ID_RE.match(canonical_id):
        raise ValueError(
            f"Normalized ID '{canonical_id}' (from '{local_id}', language='{language}') "
            f"does not conform to Canonical ID grammar"
        )

    return canonical_id
