"""Deterministic bilingual terminology annotation."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


_REASON_PRIORITY = {
    "PRODUCT_NAME": 4,
    "SEARCHABILITY": 3,
    "DOC_FREQUENCY": 2,
    "ECOSYSTEM": 1,
}
_WORD_CHARACTER = re.compile(r"[A-Za-z0-9\u3400-\u9fff]")


def generate_bilingual(
    source: str,
    target: str,
    terms: Iterable[Mapping[str, Any]],
) -> str:
    """Annotate at most two glossary terms according to SPEC §7."""
    matched: list[Mapping[str, Any]] = []
    for term in terms:
        english = term.get("en")
        chinese = term.get("zh")
        reason = term.get("reason")
        if (
            term.get("keep_en") is True
            and isinstance(english, str)
            and isinstance(chinese, str)
            and english != chinese
            and reason in _REASON_PRIORITY
            and english in source
            and chinese in target
        ):
            matched.append(term)

    selected = sorted(
        matched,
        key=lambda term: (
            -_REASON_PRIORITY[str(term["reason"])],
            -len(str(term["en"])),
            str(term["en"]),
        ),
    )[:2]
    result = target
    for term in sorted(
        selected,
        key=lambda item: (-len(str(item["zh"])), str(item["en"])),
    ):
        chinese = str(term["zh"])
        annotation = f"{chinese} ({term['en']})"
        index = result.find(chinese)
        if index < 0:
            continue
        suffix_index = index + len(chinese)
        separator = (
            " "
            if suffix_index < len(result)
            and _WORD_CHARACTER.match(result[suffix_index])
            else ""
        )
        result = (
            result[:index]
            + annotation
            + separator
            + result[suffix_index:]
        )
    return result
