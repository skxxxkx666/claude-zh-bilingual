#!/usr/bin/env python3
"""Extract printable ASCII and UTF-8 strings from binary files."""

from __future__ import annotations

import argparse
import bisect
import json
import mmap
import re
import struct
from dataclasses import dataclass
from pathlib import Path


_UTF8_CHARACTER = (
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
_PRINTABLE_RUN = re.compile(rb"(?:" + _UTF8_CHARACTER + rb"){2,}")
_EXECUTABLE = 0x20000000


@dataclass(frozen=True)
class Section:
    name: str
    start: int
    end: int
    executable: bool


def _pe_sections(path: Path) -> list[Section]:
    with path.open("rb") as source:
        header = source.read(64)
        if len(header) < 64 or header[:2] != b"MZ":
            return []
        pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
        source.seek(pe_offset)
        pe_header = source.read(24)
        if len(pe_header) < 24 or pe_header[:4] != b"PE\x00\x00":
            return []
        section_count = struct.unpack_from("<H", pe_header, 6)[0]
        optional_size = struct.unpack_from("<H", pe_header, 20)[0]
        source.seek(optional_size, 1)
        sections: list[Section] = []
        for _ in range(section_count):
            section = source.read(40)
            if len(section) < 40:
                break
            name = section[:8].rstrip(b"\x00").decode("ascii", errors="replace")
            raw_size = struct.unpack_from("<I", section, 16)[0]
            raw_offset = struct.unpack_from("<I", section, 20)[0]
            characteristics = struct.unpack_from("<I", section, 36)[0]
            sections.append(
                Section(
                    name=name,
                    start=raw_offset,
                    end=raw_offset + raw_size,
                    executable=bool(characteristics & _EXECUTABLE),
                )
            )
    return sorted(sections, key=lambda item: item.start)


def _section_at(
    sections: list[Section],
    starts: list[int],
    offset: int,
) -> Section | None:
    if not sections:
        return None
    index = bisect.bisect_right(starts, offset) - 1
    if index < 0:
        return None
    section = sections[index]
    return section if offset < section.end else None


def extract(
    source_path: Path,
    output_path: Path,
    target: str,
    version: str,
) -> int:
    sections = _pe_sections(source_path)
    section_starts = [section.start for section in sections]
    count = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with source_path.open("rb") as source, output_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
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
                section = _section_at(sections, section_starts, match.start())
                record = {
                    "source": text,
                    "target": target,
                    "version": version,
                    "extractor": "binary",
                    "container": str(source_path.resolve()),
                    "offset": match.start(),
                    "offset_unit": "byte",
                    "byte_length": len(raw),
                    "encoding": "ascii" if is_ascii else "utf-8",
                    "context": {
                        "section": section.name if section else None,
                        "section_executable": (
                            section.executable if section else None
                        ),
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
