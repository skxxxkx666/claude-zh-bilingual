#!/usr/bin/env python3
"""Compare sampled Desktop JavaScript strings with the packaged locale catalog."""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path


_COMMON_UI_WORDS = {
    "add",
    "allow",
    "cancel",
    "close",
    "continue",
    "copy",
    "delete",
    "done",
    "edit",
    "error",
    "find",
    "loading",
    "open",
    "remove",
    "retry",
    "save",
    "search",
    "warning",
}


def _looks_like_ui(text: str) -> bool:
    stripped = text.strip()
    if not 4 <= len(stripped) <= 120:
        return False
    if not stripped.isascii() or not re.search(r"\s", stripped):
        return False
    if any(marker in stripped for marker in ("http://", "https://", "::", "\\\\")):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", stripped)
    if len(words) < 2:
        return False
    first_word = stripped.split(maxsplit=1)[0].casefold()
    if not (stripped[0].isupper() or first_word in _COMMON_UI_WORDS):
        return False
    return sum(character.isalpha() for character in stripped) / len(stripped) >= 0.55


def _reservoir(
    sample: list[dict[str, object]],
    item: dict[str, object],
    seen: int,
    limit: int,
    rng: random.Random,
) -> None:
    if len(sample) < limit:
        sample.append(item)
        return
    position = rng.randrange(seen)
    if position < limit:
        sample[position] = item


def compare(
    locale_path: Path,
    literals_paths: list[Path],
    output_path: Path,
) -> None:
    messages = json.loads(locale_path.read_text(encoding="utf-8"))
    locale_values = set(messages.values())
    rng = random.Random(18286)
    hardcoded_sample: list[dict[str, object]] = []
    localized_sample: list[dict[str, object]] = []
    hardcoded_seen = 0
    localized_seen = 0
    total_occurrences = 0
    localized_occurrences = 0
    unique_candidates: set[str] = set()
    unique_localized: set[str] = set()
    per_file: list[dict[str, object]] = []

    for literals_path in literals_paths:
        file_occurrences = 0
        file_localized = 0
        file_unique: set[str] = set()
        file_unique_localized: set[str] = set()
        with literals_path.open("r", encoding="utf-8") as records:
            for line in records:
                record = json.loads(line)
                value = record["value"]
                if not _looks_like_ui(value):
                    continue
                file_occurrences += 1
                total_occurrences += 1
                file_unique.add(value)
                unique_candidates.add(value)
                view = {
                    "file": literals_path.name,
                    "line": record["line"],
                    "value": value,
                }
                if value in locale_values:
                    file_localized += 1
                    localized_occurrences += 1
                    file_unique_localized.add(value)
                    unique_localized.add(value)
                    localized_seen += 1
                    _reservoir(
                        localized_sample,
                        view,
                        localized_seen,
                        20,
                        rng,
                    )
                else:
                    hardcoded_seen += 1
                    _reservoir(
                        hardcoded_sample,
                        view,
                        hardcoded_seen,
                        40,
                        rng,
                    )
        per_file.append(
            {
                "file": literals_path.name,
                "candidate_occurrences": file_occurrences,
                "localized_occurrences": file_localized,
                "potential_hardcoded_occurrences": (
                    file_occurrences - file_localized
                ),
                "unique_candidates": len(file_unique),
                "unique_localized": len(file_unique_localized),
            }
        )

    analysis = {
        "locale_file": str(locale_path.resolve()),
        "locale_key_count": len(messages),
        "locale_unique_value_count": len(locale_values),
        "candidate_occurrences": total_occurrences,
        "localized_occurrences": localized_occurrences,
        "potential_hardcoded_occurrences": (
            total_occurrences - localized_occurrences
        ),
        "potential_hardcoded_ratio": (
            round(
                (total_occurrences - localized_occurrences)
                / total_occurrences,
                4,
            )
            if total_occurrences
            else 0
        ),
        "unique_candidates": len(unique_candidates),
        "unique_localized": len(unique_localized),
        "unique_potential_hardcoded": len(
            unique_candidates - unique_localized
        ),
        "per_file": per_file,
        "localized_sample": localized_sample,
        "potential_hardcoded_sample": hardcoded_sample,
    }
    output_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("locale", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("literals", nargs="+", type=Path)
    args = parser.parse_args()
    compare(args.locale, args.literals, args.output)


if __name__ == "__main__":
    main()
