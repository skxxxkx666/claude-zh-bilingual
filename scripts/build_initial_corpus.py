#!/usr/bin/env python3
"""Build a deterministic, untranslated corpus from classified JSONL queues."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corelib import display_width, extract_placeholders, unit_id  # noqa: E402


_RISKS = {"DANGER", "FRAGILE", "UNKNOWN"}
_RISK_PRIORITY = {"DANGER": 3, "FRAGILE": 2, "UNKNOWN": 1}


def _records(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        with path.open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"{path}:{line_number}: {error}") from error
                if not isinstance(record, dict):
                    raise ValueError(f"{path}:{line_number}: record must be an object")
                yield record


def _record_rank(record: dict[str, Any]) -> tuple[int, int, str]:
    source = record["source"]
    return (
        -_RISK_PRIORITY[record["risk"]],
        len(source.encode("utf-8")),
        source,
    )


def build_corpus(
    target: str,
    version: str,
    inputs: Iterable[Path],
    generated_at: str,
    included_sources: set[str] | None = None,
) -> tuple[dict[str, Any], Counter[str]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    stats: Counter[str] = Counter()
    for record in _records(inputs):
        stats["input_records"] += 1
        source = record.get("source")
        risk = record.get("risk")
        if not isinstance(source, str) or not source:
            stats["rejected_empty"] += 1
            continue
        if included_sources is not None and source not in included_sources:
            stats["rejected_unselected"] += 1
            continue
        if len(source) > 500:
            stats["rejected_over_500"] += 1
            continue
        try:
            source.encode("utf-8")
        except UnicodeEncodeError:
            stats["rejected_invalid_unicode"] += 1
            continue
        if risk not in _RISKS:
            stats["rejected_invalid_risk"] += 1
            continue
        grouped.setdefault(unit_id(source), []).append(record)

    units: list[dict[str, Any]] = []
    for identifier, variants in grouped.items():
        distinct_sources = {record["source"] for record in variants}
        stats["duplicate_records"] += len(variants) - len(distinct_sources)
        if len(distinct_sources) > 1:
            stats["normalized_id_collisions"] += 1
        representative = min(variants, key=_record_rank)
        source = representative["source"]
        risk = representative["risk"]
        reason = representative.get("risk_reason")
        surface = (
            "desktop.locale.catalog"
            if representative.get("context", {}).get("source_kind") == "locale"
            else "cli.ast.literal"
        )
        units.append(
            {
                "id": identifier,
                "source": source,
                "target": None,
                "target_bilingual": None,
                "risk": risk,
                "risk_reason": reason if isinstance(reason, str) else None,
                "surface": surface,
                "byte_budget": len(source.encode("utf-8")),
                "display_width": display_width(source),
                "placeholders": extract_placeholders(source),
                "seen_in": [f"{target}@{version}"],
                "verified_at": None,
                "deprecated": False,
                "notes": "",
            }
        )
        stats[f"risk_{risk}"] += 1

    units.sort(key=lambda unit: unit["id"])
    stats["units"] = len(units)
    return (
        {
            "format_version": "1.0.0",
            "target": target,
            "version": version,
            "generated_at": generated_at,
            "units": units,
        },
        stats,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=("cli", "desktop"))
    parser.add_argument("version")
    parser.add_argument("output", type=Path)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--generated-at")
    parser.add_argument("--include-source", action="append")
    args = parser.parse_args()
    generated_at = args.generated_at or (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    corpus, stats = build_corpus(
        args.target,
        args.version,
        args.inputs,
        generated_at,
        set(args.include_source) if args.include_source else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as destination:
        json.dump(corpus, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
    print(json.dumps(dict(sorted(stats.items())), indent=2))


if __name__ == "__main__":
    main()
