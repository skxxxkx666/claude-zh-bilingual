#!/usr/bin/env python3
"""Measure conservative pixel-difference area between Desktop screenshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops


def compare(
    baseline_path: Path,
    current_path: Path,
    threshold: int,
    diff_path: Path | None,
) -> dict[str, int | float | str]:
    baseline = Image.open(baseline_path).convert("RGB")
    current = Image.open(current_path).convert("RGB")
    if baseline.size != current.size:
        raise ValueError(
            f"screenshot sizes differ: {baseline.size} != {current.size}"
        )

    difference = ImageChops.difference(baseline, current)
    mask = difference.convert("L").point(
        lambda value: 255 if value > threshold else 0
    )
    histogram = mask.histogram()
    changed_pixels = sum(histogram[1:])
    total_pixels = baseline.width * baseline.height
    changed_ratio = changed_pixels / total_pixels

    if diff_path is not None:
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        overlay = current.copy()
        red = Image.new("RGB", current.size, (255, 40, 40))
        overlay.paste(red, mask=mask.point(lambda value: value // 2))
        overlay.save(diff_path)

    return {
        "baseline": str(baseline_path),
        "current": str(current_path),
        "width": baseline.width,
        "height": baseline.height,
        "threshold": threshold,
        "changed_pixels": changed_pixels,
        "total_pixels": total_pixels,
        "changed_ratio": changed_ratio,
        "changed_percent": changed_ratio * 100,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("--threshold", type=int, default=24)
    parser.add_argument("--limit", type=float, default=0.05)
    parser.add_argument("--diff", type=Path)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 255:
        parser.error("--threshold must be between 0 and 255")
    if not 0 <= args.limit <= 1:
        parser.error("--limit must be between 0 and 1")

    result = compare(
        args.baseline,
        args.current,
        args.threshold,
        args.diff,
    )
    result["limit"] = args.limit
    result["passed"] = result["changed_ratio"] < args.limit
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
