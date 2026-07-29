"""Canonical text algorithms defined by docs/SPEC.md."""

from __future__ import annotations

import hashlib
import re
import unicodedata


_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_PLACEHOLDER = re.compile(
    r"\$\{[^}]*\}"
    r"|%\d+\$[sdifx]"
    r"|\{[a-zA-Z0-9_]*\}"
    r"|%[sdifx]"
)
_PLACEHOLDER_TOKEN = "\x00PH\x00"


def extract_placeholders(text: str) -> list[str]:
    """Return placeholder spellings in source order, including repeats."""
    return [match.group(0) for match in _PLACEHOLDER.finditer(text)]


def normalize(text: str) -> str:
    """Normalize source text exactly as specified for translation-unit IDs."""
    normalized = _ANSI.sub("", text)
    normalized = unicodedata.normalize("NFC", normalized)
    normalized = _PLACEHOLDER.sub(lambda _: _PLACEHOLDER_TOKEN, normalized)
    return normalized.strip()


def unit_id(text: str) -> str:
    """Return the first 16 hexadecimal digits of normalized SHA-256."""
    digest = hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()
    return digest[:16]


def display_width(text: str) -> int:
    """Return terminal column width using the project's Unicode rules."""
    width = 0
    for character in text:
        category = unicodedata.category(character)
        if category in {"Mn", "Me", "Cc"}:
            continue
        width += (
            2
            if unicodedata.east_asian_width(character) in {"W", "F"}
            else 1
        )
    return width
