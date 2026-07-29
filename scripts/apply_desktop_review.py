#!/usr/bin/env python3
"""Apply a manually reviewed Desktop translation list to the corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corelib import generate_bilingual  # noqa: E402


PENDING_NOTE = "W3 manual review; pending D1-D4 verification"
VERIFIED_NOTE = "W3 manual review; D1-D4 verified"
MANAGED_NOTES = {PENDING_NOTE, VERIFIED_NOTE}


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def apply_review(
    corpus_path: Path,
    glossary_path: Path,
    review_path: Path,
    verified_at: str | None = None,
) -> tuple[dict[str, Any], int]:
    corpus = _read_json(corpus_path)
    glossary = _read_json(glossary_path)
    reviews = _read_json(review_path)

    if corpus.get("target") != "desktop":
        raise ValueError(f"{corpus_path} is not a Desktop corpus")
    if not isinstance(reviews, list):
        raise ValueError(f"{review_path} must contain a JSON array")

    units = {unit["id"]: unit for unit in corpus["units"]}
    terms = glossary["terms"]
    seen_ids: set[str] = set()
    managed_note = VERIFIED_NOTE if verified_at else PENDING_NOTE
    provided_ids = {
        review.get("id")
        for review in reviews
        if isinstance(review, dict) and isinstance(review.get("id"), str)
    }

    for unit in corpus["units"]:
        if unit.get("notes") in MANAGED_NOTES and unit["id"] not in provided_ids:
            unit["target"] = None
            unit["target_bilingual"] = None
            unit["risk"] = "UNKNOWN"
            unit["risk_reason"] = "R-UITEXT"
            unit["verified_at"] = None
            unit["notes"] = ""

    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            raise ValueError(f"review[{index}] must be an object")
        allowed_keys = {"id", "source", "target"}
        if set(review) not in ({"id", "target"}, allowed_keys):
            raise ValueError(
                f"review[{index}] must contain id and target, with optional source"
            )

        identifier = review["id"]
        target = review["target"]
        if not all(isinstance(value, str) for value in (identifier, target)):
            raise ValueError(f"review[{index}] values must be strings")
        if identifier in seen_ids:
            raise ValueError(f"duplicate reviewed id {identifier}")
        seen_ids.add(identifier)

        unit = units.get(identifier)
        if unit is None:
            raise ValueError(f"unknown reviewed id {identifier}")
        source = unit["source"]
        if "source" in review and review["source"] != source:
            raise ValueError(f"source mismatch for {identifier}")
        is_review_reapply = (
            unit["risk"] == "SAFE"
            and unit.get("notes") in MANAGED_NOTES
        )
        if unit["risk"] != "UNKNOWN" and not is_review_reapply:
            raise ValueError(
                f"{identifier} has risk {unit['risk']}, expected UNKNOWN or W3 review"
            )
        if unit["surface"] != "desktop.locale.catalog":
            raise ValueError(
                f"{identifier} is not a Desktop locale catalog string"
            )
        if not target.strip() or target == source:
            raise ValueError(f"{identifier} has an invalid reviewed target")

        unit["target"] = target
        unit["target_bilingual"] = generate_bilingual(source, target, terms)
        unit["risk"] = "SAFE"
        unit["risk_reason"] = "manual review: locale catalog display string"
        unit["verified_at"] = verified_at
        unit["notes"] = managed_note

    return corpus, len(seen_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path, help="review JSON file")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=ROOT / "corpus" / "desktop" / "1.18286.0.json",
    )
    parser.add_argument(
        "--glossary",
        type=Path,
        default=ROOT / "corpus" / "glossary.json",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the updated corpus instead of only checking the review",
    )
    parser.add_argument(
        "--verified-at",
        help="set verified_at after all D1-D4 assertions have passed",
    )
    args = parser.parse_args()

    corpus, reviewed_count = apply_review(
        args.corpus,
        args.glossary,
        args.review,
        args.verified_at,
    )
    if args.write:
        temporary_path = args.corpus.with_suffix(".json.tmp")
        with temporary_path.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(corpus, output, ensure_ascii=False, indent=2)
            output.write("\n")
        temporary_path.replace(args.corpus)
        print(f"applied {reviewed_count} reviewed Desktop translation(s)")
    else:
        print(f"checked {reviewed_count} reviewed Desktop translation(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
