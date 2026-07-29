#!/usr/bin/env python3
"""Create an isolated equal-length probe patch for a Bun PE snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


BUN_STRING_TAG = 9


@dataclass(frozen=True)
class PeSection:
    name: str
    raw_start: int
    raw_size: int
    virtual_address: int
    virtual_size: int
    characteristics: int

    @property
    def raw_end(self) -> int:
        return self.raw_start + self.raw_size


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_pe_sections(data: bytes) -> list[PeSection]:
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("input is not a DOS/PE executable")

    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 24 > len(data) or data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError("PE signature is missing or truncated")

    section_count = struct.unpack_from("<H", data, pe_offset + 6)[0]
    optional_header_size = struct.unpack_from("<H", data, pe_offset + 20)[0]
    section_table = pe_offset + 24 + optional_header_size
    if section_table + section_count * 40 > len(data):
        raise ValueError("PE section table is truncated")

    sections: list[PeSection] = []
    for index in range(section_count):
        offset = section_table + index * 40
        name = data[offset : offset + 8].rstrip(b"\0").decode("ascii", "replace")
        virtual_size, virtual_address, raw_size, raw_start = struct.unpack_from(
            "<IIII", data, offset + 8
        )
        characteristics = struct.unpack_from("<I", data, offset + 36)[0]
        if raw_start + raw_size > len(data):
            raise ValueError(f"PE section {name!r} exceeds the input size")
        sections.append(
            PeSection(
                name=name,
                raw_start=raw_start,
                raw_size=raw_size,
                virtual_address=virtual_address,
                virtual_size=virtual_size,
                characteristics=characteristics,
            )
        )
    return sections


def _section_at(sections: list[PeSection], offset: int) -> PeSection | None:
    return next(
        (
            section
            for section in sections
            if section.raw_start <= offset < section.raw_end
        ),
        None,
    )


def _find_all(data: bytes, needle: bytes) -> list[int]:
    offsets: list[int] = []
    cursor = 0
    while True:
        offset = data.find(needle, cursor)
        if offset < 0:
            return offsets
        offsets.append(offset)
        cursor = offset + len(needle)


def plan_patch(
    data: bytes,
    source: str,
    replacement: str,
    padding: str = "equal",
) -> dict[str, Any]:
    try:
        source_bytes = source.encode("ascii")
        replacement_bytes = replacement.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("C1 probe strings must be ASCII") from error
    if not source_bytes:
        raise ValueError("source must not be empty")
    if padding not in {"equal", "nul", "space"}:
        raise ValueError(f"unsupported padding mode: {padding}")
    if padding == "equal" and len(source_bytes) != len(replacement_bytes):
        raise ValueError("C1 probe replacement must have exactly the same byte length")
    if padding != "equal" and len(replacement_bytes) >= len(source_bytes):
        raise ValueError("shortening probe replacement must be shorter than the source")

    sections = parse_pe_sections(data)
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for offset in _find_all(data, source_bytes):
        section = _section_at(sections, offset)
        record: dict[str, Any] = {
            "offset": offset,
            "section": section.name if section else None,
        }
        if section is None or section.name != ".bun":
            record["reason"] = "outside .bun"
            skipped.append(record)
            continue
        if offset < 8:
            record["reason"] = "missing Bun string header"
            skipped.append(record)
            continue

        tag, stored_length = struct.unpack_from("<II", data, offset - 8)
        record.update({"tag": tag, "stored_length": stored_length})
        if tag != BUN_STRING_TAG or stored_length != len(source_bytes):
            record["reason"] = "Bun string header mismatch"
            skipped.append(record)
            continue
        accepted.append(record)

    return {
        "source": source,
        "replacement": replacement,
        "padding": padding,
        "byte_length": len(source_bytes),
        "matches": len(accepted) + len(skipped),
        "accepted": accepted,
        "skipped": skipped,
        "sections": [
            {
                **asdict(section),
                "raw_end": section.raw_end,
                "characteristics": f"0x{section.characteristics:08x}",
            }
            for section in sections
        ],
    }


def create_probe(
    input_path: Path,
    output_path: Path,
    source: str,
    replacement: str,
    padding: str = "equal",
) -> dict[str, Any]:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("probe output must not overwrite the input")

    original = input_path.read_bytes()
    plan = plan_patch(original, source, replacement, padding)
    if not plan["accepted"]:
        raise ValueError("no validated Bun string occurrences were found")

    source_bytes = source.encode("ascii")
    replacement_bytes = replacement.encode("ascii")
    if padding == "nul":
        stored_bytes = replacement_bytes.ljust(len(source_bytes), b"\0")
    elif padding == "space":
        stored_bytes = replacement_bytes.ljust(len(source_bytes), b" ")
    else:
        stored_bytes = replacement_bytes
    patched = bytearray(original)
    for occurrence in plan["accepted"]:
        offset = occurrence["offset"]
        if patched[offset : offset + len(source_bytes)] != source_bytes:
            raise RuntimeError(f"source changed before patch at offset {offset}")
        patched[offset : offset + len(source_bytes)] = stored_bytes
        if padding == "nul":
            struct.pack_into("<I", patched, offset - 4, len(replacement_bytes))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(patched)
    written = output_path.read_bytes()
    if len(written) != len(original):
        raise RuntimeError("probe changed the binary size")
    if input_path.read_bytes() != original:
        raise RuntimeError("probe modified the input binary")

    plan.update(
        {
            "input": str(input_path.resolve()),
            "output": str(output_path.resolve()),
            "input_sha256": _sha256(original),
            "output_sha256": _sha256(written),
            "patched_occurrences": len(plan["accepted"]),
            "input_bytes": len(original),
            "output_bytes": len(written),
        }
    )
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("source")
    parser.add_argument("replacement")
    parser.add_argument(
        "--padding",
        choices=("equal", "nul", "space"),
        default="equal",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    try:
        report = create_probe(
            args.input,
            args.output,
            args.source,
            args.replacement,
            args.padding,
        )
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"probe failed: {error}\n")

    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
