#!/usr/bin/env python3
"""Extract UI messages from a flat JSON locale catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def extract(
    source_path: Path,
    output_path: Path,
    target: str,
    version: str,
) -> int:
    with source_path.open("r", encoding="utf-8") as source:
        catalog: Any = json.load(source)
    if not isinstance(catalog, dict):
        raise ValueError("locale catalog must be a JSON object")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        for message_key, value in sorted(catalog.items()):
            if not isinstance(message_key, str) or not isinstance(value, str):
                continue
            record = {
                "source": value,
                "target": target,
                "version": version,
                "extractor": "locale-json",
                "container": str(source_path.resolve()),
                "offset": None,
                "offset_unit": None,
                "byte_length": len(value.encode("utf-8")),
                "encoding": "utf-8",
                "context": {
                    "source_kind": "locale",
                    "message_key": message_key,
                },
            }
            output.write(
                json.dumps(record, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", choices=("cli", "desktop"))
    parser.add_argument("version")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    count = extract(args.source, args.output, args.target, args.version)
    print(json.dumps({"extracted": count}))


if __name__ == "__main__":
    main()
