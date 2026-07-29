#!/usr/bin/env python3
"""Apply the ordered SPEC risk rules to extractor JSONL records."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


_PROMPT_MARKERS = (
    "You are",
    "Your task",
    "IMPORTANT:",
    "<example>",
    "<system",
    "<instructions",
)
_COMMON_UI_WORDS = {
    "cancel",
    "close",
    "continue",
    "copy",
    "delete",
    "done",
    "edit",
    "error",
    "loading",
    "open",
    "remove",
    "retry",
    "save",
    "search",
    "warning",
}


@dataclass(frozen=True)
class Classification:
    risk: str
    reason: str
    queue: str


def _looks_like_identifier(text: str) -> bool:
    stripped = text.strip()
    if not stripped or any(character.isspace() for character in stripped):
        return False
    if stripped.isupper() and any(character.isalpha() for character in stripped):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+", stripped):
        return True
    return (
        "://" in stripped
        or "::" in stripped
        or "/" in stripped
        or "\\" in stripped
        or (
            "." in stripped
            and re.fullmatch(r"[A-Za-z0-9_.@-]+", stripped) is not None
        )
    )


def _looks_like_ui(text: str, context: dict[str, Any]) -> bool:
    if context.get("source_kind") == "locale":
        return 1 <= len(text) <= 500
    stripped = text.strip()
    if not 4 <= len(stripped) <= 120 or " " not in stripped:
        return False
    first_word = stripped.split(maxsplit=1)[0].casefold()
    return stripped[0].isupper() or first_word in _COMMON_UI_WORDS


def classify_record(record: dict[str, Any]) -> Classification:
    text = record.get("source", "")
    context = record.get("context") or {}
    if context.get("property") in {"description", "parameters"}:
        return Classification("DANGER", "R-TOOLDESC", "excluded")
    if (
        context.get("comparison")
        or context.get("matcher")
        or context.get("switch_case")
    ):
        return Classification("FRAGILE", "R-CODEMATCH", "excluded")
    if (
        len(text) > 200
        and text.count(".") >= 2
        and not _looks_like_ui(text, context)
    ):
        return Classification("DANGER", "R-LONGPROSE", "excluded")
    if any(marker in text for marker in _PROMPT_MARKERS):
        return Classification("DANGER", "R-SYSPROMPT", "excluded")
    if _looks_like_identifier(text):
        return Classification("FRAGILE", "R-IDENTIFIER", "excluded")
    if _looks_like_ui(text, context):
        return Classification("UNKNOWN", "R-UITEXT", "candidates")
    return Classification("UNKNOWN", "R-DEFAULT", "unknown")


def classify_records(
    records: Iterable[dict[str, Any]],
) -> Iterable[tuple[dict[str, Any], Classification]]:
    for record in records:
        yield record, classify_record(record)


def classify_file(source: Path, output_directory: Path) -> Counter[str]:
    output_directory.mkdir(parents=True, exist_ok=True)
    destinations = {
        queue: (output_directory / f"{queue}.jsonl").open(
            "w",
            encoding="utf-8",
            newline="\n",
        )
        for queue in ("excluded", "candidates", "unknown")
    }
    stats: Counter[str] = Counter()
    try:
        with source.open("r", encoding="utf-8") as records:
            for line in records:
                record = json.loads(line)
                classification = classify_record(record)
                record["risk"] = classification.risk
                record["risk_reason"] = classification.reason
                record["queue"] = classification.queue
                destinations[classification.queue].write(
                    json.dumps(record, ensure_ascii=True, separators=(",", ":"))
                    + "\n"
                )
                stats[classification.risk] += 1
                stats[classification.reason] += 1
                stats[classification.queue] += 1
    finally:
        for destination in destinations.values():
            destination.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    stats = classify_file(args.source, args.output_directory)
    print(json.dumps(dict(sorted(stats.items())), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
