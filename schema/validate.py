#!/usr/bin/env python3
"""Validate corpus files against schemas and project semantic rules."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corelib import display_width, extract_placeholders, unit_id  # noqa: E402


_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_HAN_ASCII = re.compile(r"[\u3400-\u9fff][A-Za-z0-9]|[A-Za-z0-9][\u3400-\u9fff]")
_EMOJI = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "]"
)
_BANNED_TARGET_PARTS = ("您", "哦", "呢", "啦", "~")
_RISK_DOWNGRADE_SOURCES = {"DANGER", "FRAGILE"}


@dataclass(frozen=True)
class Issue:
    path: Path
    location: str
    reason: str

    def render(self) -> str:
        return f"{self.path}:{self.location}: {self.reason}"


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def _schema_issues(
    validator: Draft202012Validator,
    value: Any,
    path: Path,
    prefix: str,
) -> list[Issue]:
    issues: list[Issue] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.path)):
        suffix = ".".join(str(part) for part in error.path)
        location = f"{prefix}.{suffix}" if suffix else prefix
        issues.append(Issue(path, location, error.message))
    return issues


def _parse_generated_at(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _version_key(value: str) -> tuple[str, tuple[int, int, int]]:
    target, version = value.split("@", maxsplit=1)
    return target, tuple(int(part) for part in version.split("."))


def _target_text_issues(
    path: Path,
    unit_location: str,
    field: str,
    value: str,
) -> list[Issue]:
    issues: list[Issue] = []
    if any(part in value for part in _BANNED_TARGET_PARTS):
        issues.append(
            Issue(path, f"{unit_location}.{field}", "contains a banned style token")
        )
    if _EMOJI.search(value):
        issues.append(Issue(path, f"{unit_location}.{field}", "contains emoji"))
    if _HAN_ASCII.search(value):
        issues.append(
            Issue(
                path,
                f"{unit_location}.{field}",
                "must contain a half-width space between Chinese and ASCII",
            )
        )
    return issues


def _validate_glossary(
    path: Path,
    data: Any,
    validator: Draft202012Validator,
) -> tuple[list[Issue], dict[str, dict[str, Any]]]:
    issues = _schema_issues(validator, data, path, "glossary")
    terms: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    if not isinstance(data, dict) or not isinstance(data.get("terms"), list):
        return issues, terms

    for index, term in enumerate(data["terms"]):
        if not isinstance(term, dict):
            continue
        english = term.get("en")
        if not isinstance(english, str):
            continue
        if english in terms:
            issues.append(
                Issue(path, f"terms[{index}].en", f"duplicate term {english!r}")
            )
        terms[english] = term
        for alias in term.get("aliases", []):
            if alias in aliases and aliases[alias] != english:
                issues.append(
                    Issue(
                        path,
                        f"terms[{index}].aliases",
                        f"alias {alias!r} is already assigned to {aliases[alias]!r}",
                    )
                )
            aliases[alias] = english
    return issues, terms


def _validate_unit_semantics(
    path: Path,
    unit: dict[str, Any],
    index: int,
    corpus_target: str,
    glossary: dict[str, dict[str, Any]],
) -> list[Issue]:
    issues: list[Issue] = []
    identifier = unit.get("id", f"index-{index}")
    location = f"units[{index}]({identifier})"
    source = unit.get("source")
    if not isinstance(source, str):
        return issues

    expected = {
        "id": unit_id(source),
        "byte_budget": len(source.encode("utf-8")),
        "display_width": display_width(source),
        "placeholders": extract_placeholders(source),
    }
    for field, expected_value in expected.items():
        if unit.get(field) != expected_value:
            issues.append(
                Issue(
                    path,
                    f"{location}.{field}",
                    f"expected {expected_value!r}, got {unit.get(field)!r}",
                )
            )

    surface = unit.get("surface")
    if isinstance(surface, str) and not surface.startswith(f"{corpus_target}."):
        issues.append(
            Issue(
                path,
                f"{location}.surface",
                f"must start with {corpus_target!r}",
            )
        )

    seen_in = unit.get("seen_in")
    if isinstance(seen_in, list) and all(isinstance(item, str) for item in seen_in):
        if any(not item.startswith(f"{corpus_target}@") for item in seen_in):
            issues.append(
                Issue(
                    path,
                    f"{location}.seen_in",
                    f"all versions must target {corpus_target!r}",
                )
            )
        try:
            if seen_in != sorted(seen_in, key=_version_key):
                issues.append(
                    Issue(path, f"{location}.seen_in", "must be semver-sorted")
                )
        except (ValueError, IndexError):
            pass

    source_placeholders = extract_placeholders(source)
    target = unit.get("target")
    bilingual = unit.get("target_bilingual")
    for field, value in (("target", target), ("target_bilingual", bilingual)):
        if not isinstance(value, str):
            continue
        if extract_placeholders(value) != source_placeholders:
            issues.append(
                Issue(
                    path,
                    f"{location}.{field}",
                    "placeholders must match source exactly and in order",
                )
            )
        issues.extend(_target_text_issues(path, location, field, value))

    if isinstance(target, str) and display_width(target) > display_width(source):
        issues.append(
            Issue(
                path,
                f"{location}.target",
                "display width exceeds source",
            )
        )

    verified_at = unit.get("verified_at")
    if isinstance(verified_at, str) and not target:
        issues.append(
            Issue(
                path,
                f"{location}.verified_at",
                "verified unit must have a non-empty target",
            )
        )

    if isinstance(target, str) and isinstance(bilingual, str):
        annotations = 0
        for english, term in glossary.items():
            chinese = term.get("zh")
            if (
                not term.get("keep_en")
                or not isinstance(chinese, str)
                or english not in source
                or chinese not in target
            ):
                continue
            expected_annotation = f"{chinese} ({english})"
            count = bilingual.count(expected_annotation)
            if count != 1:
                issues.append(
                    Issue(
                        path,
                        f"{location}.target_bilingual",
                        f"expected one annotation {expected_annotation!r}",
                    )
                )
            annotations += count
        if annotations > 2:
            issues.append(
                Issue(
                    path,
                    f"{location}.target_bilingual",
                    "contains more than two glossary annotations",
                )
            )
    return issues


def _validate_corpus(
    path: Path,
    data: Any,
    unit_validator: Draft202012Validator,
    glossary: dict[str, dict[str, Any]],
) -> tuple[list[Issue], int]:
    issues: list[Issue] = []
    if not isinstance(data, dict):
        return [Issue(path, "root", "must be an object")], 0

    required = {"format_version", "target", "version", "generated_at", "units"}
    for field in sorted(required - set(data)):
        issues.append(Issue(path, field, "is required"))

    target = data.get("target")
    if target not in {"cli", "desktop"}:
        issues.append(Issue(path, "target", "must be 'cli' or 'desktop'"))
        target = "cli"
    for field in ("format_version", "version"):
        if not isinstance(data.get(field), str) or not _SEMVER.fullmatch(data[field]):
            issues.append(Issue(path, field, "must be a three-part semver"))
    if not _parse_generated_at(data.get("generated_at")):
        issues.append(Issue(path, "generated_at", "must be an ISO-8601 datetime"))

    units = data.get("units")
    if not isinstance(units, list):
        return issues + [Issue(path, "units", "must be an array")], 0

    identifiers: list[str] = []
    for index, unit in enumerate(units):
        prefix = f"units[{index}]"
        issues.extend(_schema_issues(unit_validator, unit, path, prefix))
        if not isinstance(unit, dict):
            continue
        if isinstance(unit.get("id"), str):
            identifiers.append(unit["id"])
        issues.extend(
            _validate_unit_semantics(path, unit, index, target, glossary)
        )

    if len(identifiers) != len(set(identifiers)):
        issues.append(Issue(path, "units", "contains duplicate ids"))
    if identifiers != sorted(identifiers):
        issues.append(Issue(path, "units", "must be sorted by id"))
    return issues, len(units)


def _discover_files(path: Path) -> tuple[Path | None, list[Path]]:
    if path.is_file():
        if path.name == "glossary.json":
            return path, []
        return None, [path]
    glossary = path / "glossary.json"
    corpus_files = sorted(
        item
        for item in path.rglob("*.json")
        if item.name != "glossary.json"
    )
    return (glossary if glossary.exists() else None), corpus_files


def _load_baseline(path: Path, ref: str) -> dict[str, Any] | None:
    try:
        relative = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return None
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _risk_downgrade_issues(
    path: Path,
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> Iterable[Issue]:
    old_risks = {
        unit.get("id"): unit.get("risk")
        for unit in baseline.get("units", [])
        if isinstance(unit, dict)
    }
    for unit in current.get("units", []):
        if not isinstance(unit, dict):
            continue
        old_risk = old_risks.get(unit.get("id"))
        if old_risk in _RISK_DOWNGRADE_SOURCES and unit.get("risk") == "SAFE":
            yield Issue(
                path,
                f"unit({unit.get('id')}).risk",
                f"{old_risk} -> SAFE requires two approvals and test evidence",
            )


def validate(
    corpus_path: Path,
    baseline_ref: str | None,
    allow_risk_downgrades: bool,
) -> tuple[list[Issue], int, int]:
    unit_schema = _read_json(ROOT / "schema" / "unit.schema.json")
    glossary_schema = _read_json(ROOT / "schema" / "glossary.schema.json")
    unit_validator = Draft202012Validator(
        unit_schema,
        format_checker=FormatChecker(),
    )
    glossary_validator = Draft202012Validator(
        glossary_schema,
        format_checker=FormatChecker(),
    )

    issues: list[Issue] = []
    glossary_path, corpus_files = _discover_files(corpus_path)
    glossary: dict[str, dict[str, Any]] = {}
    if glossary_path is not None:
        glossary_data = _read_json(glossary_path)
        glossary_issues, glossary = _validate_glossary(
            glossary_path,
            glossary_data,
            glossary_validator,
        )
        issues.extend(glossary_issues)

    unit_count = 0
    for path in corpus_files:
        data = _read_json(path)
        corpus_issues, count = _validate_corpus(
            path,
            data,
            unit_validator,
            glossary,
        )
        issues.extend(corpus_issues)
        unit_count += count
        if baseline_ref and not allow_risk_downgrades and isinstance(data, dict):
            baseline = _load_baseline(path, baseline_ref)
            if baseline is not None:
                issues.extend(_risk_downgrade_issues(path, data, baseline))
    return issues, len(corpus_files), unit_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--baseline-ref")
    parser.add_argument("--allow-risk-downgrades", action="store_true")
    args = parser.parse_args()

    try:
        issues, file_count, unit_count = validate(
            args.path,
            args.baseline_ref,
            args.allow_risk_downgrades,
        )
    except (OSError, json.JSONDecodeError) as error:
        print(f"{args.path}: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    for issue in issues:
        print(issue.render(), file=sys.stderr)
    if issues:
        print(f"validation failed with {len(issues)} issue(s)", file=sys.stderr)
        raise SystemExit(1)
    print(f"validated {file_count} corpus file(s), {unit_count} unit(s)")


if __name__ == "__main__":
    main()
