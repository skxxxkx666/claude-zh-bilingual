#!/usr/bin/env python3
"""Map native Bun strings to runtime-observed CLI help surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import re
import struct
import subprocess
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


_COMMAND = re.compile(r"^  ([a-z][a-z0-9-]*(?:\|[a-z0-9-]+)?)")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_help(value: str) -> str:
    return " ".join(value.split())


def _command_names(help_text: str) -> list[str]:
    in_commands = False
    result: list[str] = []
    for line in help_text.splitlines():
        if line.strip() == "Commands:":
            in_commands = True
            continue
        if in_commands and line and not line.startswith(" "):
            in_commands = False
        if not in_commands:
            continue
        match = _COMMAND.match(line)
        if not match:
            continue
        name = match.group(1).split("|", maxsplit=1)[0]
        if name != "help" and name not in result:
            result.append(name)
    return result


def crawl_help(claude: Path) -> dict[tuple[str, ...], str]:
    pending: deque[tuple[str, ...]] = deque([()])
    outputs: dict[tuple[str, ...], str] = {}
    while pending:
        command = pending.popleft()
        if command in outputs or len(command) > 4:
            continue
        completed = subprocess.run(
            [str(claude), *command, "--help"],
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        output = completed.stdout + completed.stderr
        if completed.returncode != 0 or "Usage:" not in output:
            continue
        outputs[command] = output
        for name in _command_names(output):
            child = (*command, name)
            if child not in outputs:
                pending.append(child)
    return outputs


def help_observations(
    outputs: dict[tuple[str, ...], str],
    sources: Iterable[str],
) -> dict[str, list[str]]:
    pages = {
        command: _normalize_help(output)
        for command, output in outputs.items()
    }
    observations: dict[str, list[str]] = defaultdict(list)
    for source in sources:
        if not source.isascii() or "\n" in source or "\r" in source:
            continue
        needle = _normalize_help(source)
        if not needle:
            continue
        for command, page in pages.items():
            if needle not in page:
                continue
            invocation = "claude"
            if command:
                invocation += f" {' '.join(command)}"
            observations[source].append(f"{invocation} --help")
    return dict(observations)


def _read_records(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
            if isinstance(record, dict):
                yield record


def validated_occurrences(
    binary: Path,
    records: Path,
    wanted_sources: set[str],
) -> dict[str, list[int]]:
    result: dict[str, list[int]] = defaultdict(list)
    with binary.open("rb") as binary_file:
        with mmap.mmap(binary_file.fileno(), length=0, access=mmap.ACCESS_READ) as data:
            for record in _read_records(records):
                source = record.get("source")
                offset = record.get("offset")
                context = record.get("context") or {}
                if (
                    source not in wanted_sources
                    or not isinstance(offset, int)
                    or context.get("section") != ".bun"
                ):
                    continue
                raw = source.encode("utf-8")
                if (
                    offset < 8
                    or data[offset : offset + len(raw)] != raw
                    or struct.unpack_from("<II", data, offset - 8) != (9, len(raw))
                ):
                    continue
                result[source].append(offset)
    return {source: sorted(set(offsets)) for source, offsets in result.items()}


def build_review(
    reference: dict[str, Any],
    occurrences: dict[str, list[int]],
    observations: dict[str, list[str]],
    version: str,
    artifact_sha256: str,
    help_pages: int,
) -> dict[str, Any]:
    approved: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for unit in reference.get("units", []):
        if unit.get("risk") != "SAFE":
            continue
        source = unit["source"]
        offsets = occurrences.get(source, [])
        evidence = observations.get(source, [])
        base = {
            "id": unit["id"],
            "source": source,
            "previous_surface": unit["surface"],
            "occurrences": offsets,
        }
        if offsets and evidence:
            approved.append(
                {
                    **base,
                    "surface": "cli.help",
                    "evidence": evidence,
                    "decision": "APPROVED",
                }
            )
        else:
            reason = (
                "not present as a validated Bun string record"
                if not offsets
                else "native record found but no runtime surface was observed"
            )
            pending.append({**base, "decision": "PENDING", "reason": reason})

    approved.sort(key=lambda item: item["id"])
    pending.sort(key=lambda item: item["id"])
    return {
        "format_version": "1.0.0",
        "target": "cli",
        "version": version,
        "artifact_sha256": artifact_sha256,
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "method": (
            "exact case-sensitive Bun string record plus verbatim runtime --help "
            "observation"
        ),
        "help_pages": help_pages,
        "approved": approved,
        "pending": pending,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("records", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("version")
    parser.add_argument("output", type=Path)
    parser.add_argument("--claude", type=Path)
    args = parser.parse_args()

    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    safe_sources = {
        unit["source"]
        for unit in reference.get("units", [])
        if unit.get("risk") == "SAFE"
    }
    occurrences = validated_occurrences(
        args.binary,
        args.records,
        safe_sources,
    )
    claude = args.claude or args.binary
    outputs = crawl_help(claude)
    observations = help_observations(outputs, safe_sources)
    review = build_review(
        reference,
        occurrences,
        observations,
        args.version,
        _sha256(args.binary),
        len(outputs),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "help_pages": len(outputs),
                "validated_sources": len(occurrences),
                "approved": len(review["approved"]),
                "pending": len(review["pending"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
