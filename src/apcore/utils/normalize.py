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
    (?<=[a-z0-9])(?=[A-Z])       # lowercase/digit → uppercase  (e.g. "http|Json")
    | (?<=[A-Z])(?=[A-Z][a-z0-9]) # uppercase run → start of word (e.g. "HTTP|Json")
    """,
    re.VERBOSE,
)

#: Canonical ID format from PROTOCOL_SPEC §2.7 EBNF grammar.
_CANONICAL_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


def _to_snake_case(segment: str) -> str:
    """Convert a PascalCase, camelCase, or mixed-case segment to snake_case."""
    if not segment:
        return segment

    res = []
    for i, char in enumerate(segment):
        if i > 0:
            prev = segment[i - 1]
            # Case 1: lowercase/digit followed by uppercase -> add underscore
            if prev.islower() or prev.isdigit():
                if char.isupper():
                    res.append("_")
            # Case 2: uppercase followed by uppercase followed by lowercase -> add underscore before the middle one
            # e.g., HTTPAPIHandler: ...PIH... -> ...PI_H...
            elif prev.isupper() and char.isupper():
                if i + 1 < len(segment) and segment[i + 1].islower():
                    res.append("_")
        res.append(char.lower())
    
    return "".join(res).replace("__", "_")


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
