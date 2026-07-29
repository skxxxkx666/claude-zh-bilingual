#!/usr/bin/env python3
"""Review CLI candidates that are observed verbatim in read-only --help output."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corelib import display_width, extract_placeholders, unit_id  # noqa: E402


VERSION = "2.1.112"
TARGET_COUNT = 400
DISALLOWED = (
    "${",
    "you are ",
    "system prompt",
    "prompt text",
    "tool description",
    "api key",
    "api-key",
    "oauth",
    "idp",
    "access token",
    "refresh token",
    "token",
    "authenticate",
    "authentication",
    "authorize",
    "authorization",
    "login",
    "log in",
    "log out",
    "sign in",
    "sign out",
    "account",
    "credential",
    "secret",
    "password",
    "billing",
    "fund",
    "credit",
    "subscription",
    "dollar",
    "spend",
    "usage",
    "add funds",
    "extra usage",
    "certificate",
    "private key",
    "proxy",
    "aws profile",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
            if isinstance(record, dict):
                records.append(record)
    return records


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
        match = re.match(r"^  ([a-z][a-z0-9-]*(?:\|[a-z0-9-]+)?)", line)
        if not match:
            continue
        name = match.group(1).split("|", maxsplit=1)[0]
        if name != "help" and name not in result:
            result.append(name)
    return result


def _crawl_help(claude: str) -> dict[tuple[str, ...], str]:
    pending: deque[tuple[str, ...]] = deque([()])
    outputs: dict[tuple[str, ...], str] = {}
    while pending:
        command = pending.popleft()
        if command in outputs or len(command) > 4:
            continue
        completed = subprocess.run(
            [claude, *command, "--help"],
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


def _eligible(source: str) -> bool:
    if not 2 <= len(source) <= 200:
        return False
    if not source.isascii() or "\n" in source or "\r" in source:
        return False
    lowered = source.lower()
    if any(token in lowered for token in DISALLOWED):
        return False
    if any(character in source for character in "{}[]`"):
        return False
    if not re.search(r"[A-Za-z]", source):
        return False
    return True


def _observations(
    outputs: dict[tuple[str, ...], str],
    candidate_sources: set[str],
) -> dict[str, list[str]]:
    normalized_pages = {
        command: _normalize_help(output)
        for command, output in outputs.items()
    }
    result: dict[str, list[str]] = defaultdict(list)
    for source in candidate_sources:
        if not _eligible(source):
            continue
        needle = _normalize_help(source)
        for command, page in normalized_pages.items():
            if needle in page:
                invocation = "claude"
                if command:
                    invocation += f" {' '.join(command)}"
                result[source].append(f"{invocation} --help")
    return result


def _safe_sources(
    classified: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    observations: dict[str, list[str]],
) -> list[str]:
    risks: dict[str, set[str]] = defaultdict(set)
    for record in classified:
        source = record.get("source")
        risk = record.get("risk")
        if isinstance(source, str) and isinstance(risk, str):
            risks[source].add(risk)
    candidate_counts: dict[str, int] = defaultdict(int)
    for record in candidates:
        source = record.get("source")
        if isinstance(source, str):
            candidate_counts[source] += 1

    ranked = [
        source
        for source in observations
        if risks.get(source, {"UNKNOWN"}) <= {"UNKNOWN"}
    ]
    ranked.sort(
        key=lambda source: (
            -len(observations[source]),
            -candidate_counts[source],
            len(source),
            source,
        )
    )
    return ranked


def _manual_sources(
    path: Path,
    candidate_sources: set[str],
    classified: list[dict[str, Any]],
) -> tuple[list[str], dict[str, list[str]], dict[str, int]]:
    with path.open("r", encoding="utf-8") as source:
        proposals = json.load(source)
    if not isinstance(proposals, list) or not all(
        isinstance(item, str) for item in proposals
    ):
        raise ValueError(f"{path} must contain an array of strings")
    risks: dict[str, set[str]] = defaultdict(set)
    for record in classified:
        source = record.get("source")
        risk = record.get("risk")
        if isinstance(source, str) and isinstance(risk, str):
            risks[source].add(risk)
    selected: list[str] = []
    rejected_missing = 0
    rejected_risk = 0
    rejected_content = 0
    for source in proposals:
        if source not in candidate_sources:
            rejected_missing += 1
            continue
        if not risks.get(source, {"UNKNOWN"}) <= {"UNKNOWN"}:
            rejected_risk += 1
            continue
        if not _eligible(source):
            rejected_content += 1
            continue
        if source not in selected:
            selected.append(source)
    evidence = {
        source: [f"manual review of extracted cli@{VERSION} candidate occurrence"]
        for source in selected
    }
    return (
        selected,
        evidence,
        {
            "manual_proposals": len(proposals),
            "manual_accepted": len(selected),
            "manual_rejected_missing": rejected_missing,
            "manual_rejected_risk": rejected_risk,
            "manual_rejected_content": rejected_content,
        },
    )


def _review_reason(evidence: list[str]) -> str:
    if any(item.endswith("--help") for item in evidence):
        return "verbatim read-only --help display text; no DANGER or FRAGILE occurrence"
    return (
        "manually reviewed visible CLI candidate; "
        "no DANGER or FRAGILE occurrence"
    )


def _is_managed_unit(unit: dict[str, Any]) -> bool:
    notes = unit.get("notes", "")
    return notes.startswith(("W5 help review:", "W5 CLI review:"))


def _write_review(path: Path, sources: list[str], observations: dict[str, list[str]]) -> None:
    payload = [
        {
            "source": source,
            "evidence": observations[source],
            "decision": "SAFE",
            "reason": _review_reason(observations[source]),
        }
        for source in sources
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
        output.write("\n")
    temporary.replace(path)


def _apply_corpus(
    path: Path,
    sources: list[str],
    observations: dict[str, list[str]],
) -> None:
    with path.open("r", encoding="utf-8") as source_file:
        corpus = json.load(source_file)
    corpus["units"] = [
        unit
        for unit in corpus["units"]
        if not (
            _is_managed_unit(unit)
            and unit["source"] not in set(sources)
        )
    ]
    units = {unit["source"]: unit for unit in corpus["units"]}
    for source in sources:
        evidence = observations[source][0]
        risk_reason = f"manual review: {_review_reason(observations[source])}"
        surface = (
            "cli.help"
            if any(item.endswith("--help") for item in observations[source])
            else "cli.visible"
        )
        unit = units.get(source)
        if unit is None:
            unit = {
                "id": unit_id(source),
                "source": source,
                "target": None,
                "target_bilingual": None,
                "risk": "SAFE",
                "risk_reason": risk_reason,
                "surface": surface,
                "byte_budget": len(source.encode("utf-8")),
                "display_width": display_width(source),
                "placeholders": extract_placeholders(source),
                "seen_in": [f"cli@{VERSION}"],
                "verified_at": None,
                "deprecated": False,
                "notes": f"W5 CLI review: {evidence}",
            }
            corpus["units"].append(unit)
            units[source] = unit
        else:
            if unit["risk"] not in {"UNKNOWN", "SAFE"}:
                raise ValueError(
                    f"refusing to lower {source!r} from {unit['risk']} to SAFE"
                )
            unit["risk"] = "SAFE"
            unit["risk_reason"] = risk_reason
            unit["surface"] = surface
            unit["target"] = None
            unit["target_bilingual"] = None
            unit["verified_at"] = None
            unit["notes"] = f"W5 CLI review: {evidence}"
    corpus["generated_at"] = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    corpus["units"].sort(key=lambda unit: unit["id"])
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(corpus, output, ensure_ascii=False, indent=2)
        output.write("\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude", default=shutil.which("claude"))
    parser.add_argument("--count", type=int, default=TARGET_COUNT)
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--candidates",
        type=Path,
        default=ROOT / "extracted" / f"cli-{VERSION}-queues" / "candidates.jsonl",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=ROOT / "corpus" / "cli" / f"{VERSION}.json",
    )
    parser.add_argument(
        "--review",
        type=Path,
        default=ROOT / "reviews" / f"cli-{VERSION}-w5-help.json",
    )
    parser.add_argument(
        "--manual",
        type=Path,
        default=ROOT / "reviews" / f"cli-{VERSION}-w5-manual-sources.json",
    )
    args = parser.parse_args()
    if not args.claude:
        raise SystemExit("claude executable was not found")
    if not 400 <= args.count <= 800:
        raise SystemExit("--count must stay within the W5 review target of 400-800")

    outputs = _crawl_help(args.claude)
    candidates = _read_jsonl(args.candidates)
    classified = []
    for queue in sorted(args.candidates.parent.glob("*.jsonl")):
        classified.extend(_read_jsonl(queue))
    candidate_sources = {
        record["source"]
        for record in candidates
        if isinstance(record.get("source"), str)
    }
    observations = _observations(outputs, candidate_sources)
    help_sources = _safe_sources(classified, candidates, observations)
    manual_sources, manual_evidence, manual_stats = _manual_sources(
        args.manual,
        candidate_sources,
        classified,
    )
    for source, evidence in manual_evidence.items():
        observed = observations.setdefault(source, [])
        observed.extend(item for item in evidence if item not in observed)
    safe_sources = list(help_sources)
    safe_sources.extend(
        source for source in manual_sources if source not in set(safe_sources)
    )
    with args.corpus.open("r", encoding="utf-8") as source:
        current_corpus = json.load(source)
    existing_by_id = {
        unit["id"]: unit
        for unit in current_corpus["units"]
        if not _is_managed_unit(unit)
    }
    unique_sources = []
    selected_ids: set[str] = set()
    for source in safe_sources:
        identifier = unit_id(source)
        existing = existing_by_id.get(identifier)
        if existing is not None and existing["source"] != source:
            continue
        if identifier in selected_ids:
            continue
        selected_ids.add(identifier)
        unique_sources.append(source)
    safe_sources = unique_sources
    print(
        json.dumps(
            {
                "help_pages": len(outputs),
                "candidate_sources_observed": len(observations),
                "help_safe_sources": len(help_sources),
                "conservative_safe_sources": len(safe_sources),
                "requested": args.count,
                **manual_stats,
            },
            indent=2,
        )
    )
    if len(safe_sources) < args.count:
        raise SystemExit(
            f"only {len(safe_sources)} conservative sources were observed; "
            f"refusing to invent {args.count - len(safe_sources)} SAFE decisions"
        )
    selected = safe_sources[: args.count]
    if args.write:
        _write_review(args.review, selected, observations)
        _apply_corpus(args.corpus, selected, observations)
        print(f"wrote {len(selected)} reviewed SAFE source(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
