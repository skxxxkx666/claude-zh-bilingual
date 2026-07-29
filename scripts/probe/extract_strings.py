#!/usr/bin/env python3
"""Extract printable ASCII and UTF-8 strings from a binary for M1 probing."""

from __future__ import annotations

import argparse
import json
import mmap
import random
import re
import statistics
from pathlib import Path


_UTF8_CHAR = (
    rb"(?:"
    rb"[\x20-\x7e]"
    rb"|[\xc2-\xdf][\x80-\xbf]"
    rb"|\xe0[\xa0-\xbf][\x80-\xbf]"
    rb"|[\xe1-\xec\xee-\xef][\x80-\xbf]{2}"
    rb"|\xed[\x80-\x9f][\x80-\xbf]"
    rb"|\xf0[\x90-\xbf][\x80-\xbf]{2}"
    rb"|[\xf1-\xf3][\x80-\xbf]{3}"
    rb"|\xf4[\x80-\x8f][\x80-\xbf]{2}"
    rb")"
)
_PRINTABLE_RUN = re.compile(rb"(?:" + _UTF8_CHAR + rb"){2,}")
_WHITESPACE = re.compile(r"\s")

_KNOWN_TEXTS = (
    "Press Shift+Tab",
    "auto-accept edits",
    "Continue",
    "Permission denied",
    "Thinking",
    "context left",
    "Photosynthesizing",
)


def _is_ui_candidate(text: str) -> bool:
    stripped = text.strip()
    if not 4 <= len(stripped) <= 120:
        return False
    if not stripped[0].isupper() or not _WHITESPACE.search(stripped):
        return False
    return not any(marker in stripped for marker in ("/", "\\", "::", "_"))


def _is_plausible_ui_candidate(text: str) -> bool:
    if not _is_ui_candidate(text) or not text.isascii():
        return False
    stripped = text.strip()
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", stripped)
    letter_ratio = sum(character.isalpha() for character in stripped) / len(stripped)
    return len(words) >= 2 and letter_ratio >= 0.55


def _length_summary(lengths: list[int]) -> dict[str, float | int] | None:
    if not lengths:
        return None
    return {
        "count": len(lengths),
        "min": min(lengths),
        "max": max(lengths),
        "mean": round(statistics.fmean(lengths), 2),
        "median": statistics.median(lengths),
    }


def extract(binary_path: Path, output_path: Path, analysis_path: Path) -> None:
    file_size = binary_path.stat().st_size
    counts = {"ascii": 0, "utf8": 0}
    extracted_bytes = 0
    candidate_count = 0
    plausible_candidate_count = 0
    candidate_sample: list[dict[str, object]] = []
    known_hits: dict[str, dict[str, list[dict[str, int]]]] = {
        text: {"exact": [], "containing": []} for text in _KNOWN_TEXTS
    }
    rng = random.Random(2112)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with binary_path.open("rb") as source, output_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as output:
        with mmap.mmap(source.fileno(), length=0, access=mmap.ACCESS_READ) as data:
            for match in _PRINTABLE_RUN.finditer(data):
                raw = match.group()
                is_ascii = raw.isascii()
                if is_ascii and len(raw) < 4:
                    continue

                try:
                    text = raw.decode("ascii" if is_ascii else "utf-8")
                except UnicodeDecodeError:
                    continue
                if not text.isprintable():
                    continue

                encoding = "ascii" if is_ascii else "utf8"
                record = {
                    "content": text,
                    "offset": match.start(),
                    "byte_length": len(raw),
                    "encoding": encoding,
                }
                output.write(
                    json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
                counts[encoding] += 1
                extracted_bytes += len(raw)

                if _is_ui_candidate(text):
                    candidate_count += 1

                if _is_plausible_ui_candidate(text):
                    plausible_candidate_count += 1
                    sample_record = {
                        "content": text,
                        "offset": match.start(),
                        "byte_length": len(raw),
                    }
                    if len(candidate_sample) < 30:
                        candidate_sample.append(sample_record)
                    else:
                        position = rng.randrange(plausible_candidate_count)
                        if position < 30:
                            candidate_sample[position] = sample_record

                lower_text = text.casefold()
                for known_text in _KNOWN_TEXTS:
                    known_lower = known_text.casefold()
                    hit = {
                        "offset": match.start(),
                        "byte_length": len(raw),
                    }
                    if lower_text == known_lower:
                        known_hits[known_text]["exact"].append(hit)
                    elif (
                        known_lower in lower_text
                        and len(known_hits[known_text]["containing"]) < 10
                    ):
                        known_hits[known_text]["containing"].append(hit)

    sample_lengths = [int(item["byte_length"]) for item in candidate_sample]
    total_strings = counts["ascii"] + counts["utf8"]
    analysis = {
        "binary": str(binary_path.resolve()),
        "binary_bytes": file_size,
        "total_strings": total_strings,
        "ascii_strings": counts["ascii"],
        "utf8_strings": counts["utf8"],
        "extracted_string_bytes": extracted_bytes,
        "extracted_bytes_ratio": round(extracted_bytes / file_size, 6),
        "ui_candidate_count": candidate_count,
        "ui_candidate_ratio": (
            round(candidate_count / total_strings, 6) if total_strings else 0
        ),
        "plausible_ui_candidate_count": plausible_candidate_count,
        "known_text_hits": known_hits,
        "ui_candidate_sample": candidate_sample,
        "ui_candidate_sample_byte_lengths": _length_summary(sample_lengths),
    }
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    analysis_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("analysis", type=Path)
    args = parser.parse_args()
    extract(args.binary, args.output, args.analysis)


if __name__ == "__main__":
    main()
