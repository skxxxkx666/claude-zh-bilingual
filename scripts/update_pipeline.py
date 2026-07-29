#!/usr/bin/env python3
"""Detect upstream versions and run the isolated corpus update pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corelib.pipeline import inherit_corpus, read_jsonl, render_pr_body  # noqa: E402


NPM_LATEST_URL = (
    "https://registry.npmjs.org/@anthropic-ai%2Fclaude-code/latest"
)
DESKTOP_LATEST_URL = (
    "https://claude.ai/api/desktop/win32/x64/setup/latest/redirect"
)
_SEMVER = re.compile(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: BinaryIO,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def semver_key(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError(f"not a three-part semver: {value}")
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def known_versions(target: str, corpus_root: Path = ROOT / "corpus") -> list[str]:
    versions: set[str] = set()
    for path in (corpus_root / target).glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as source:
                data = json.load(source)
        except (OSError, json.JSONDecodeError):
            continue
        version = data.get("version") if isinstance(data, dict) else None
        if isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version):
            versions.add(version)
    return sorted(versions, key=semver_key)


def merge_corpus_history(
    target: str,
    corpus_root: Path = ROOT / "corpus",
) -> dict[str, Any]:
    """Build an in-memory inheritance base without changing existing corpus files."""
    corpora: list[dict[str, Any]] = []
    for path in (corpus_root / target).glob("*.json"):
        try:
            data = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        version = data.get("version") if isinstance(data, dict) else None
        units = data.get("units") if isinstance(data, dict) else None
        if (
            isinstance(version, str)
            and re.fullmatch(r"\d+\.\d+\.\d+", version)
            and isinstance(units, list)
        ):
            corpora.append(data)
    if not corpora:
        raise ValueError(f"no semver corpus files found for {target}")
    corpora.sort(key=lambda item: semver_key(item["version"]))
    merged: dict[str, dict[str, Any]] = {}
    for corpus in corpora:
        for candidate in corpus["units"]:
            if not isinstance(candidate, dict) or not isinstance(
                candidate.get("id"),
                str,
            ):
                continue
            identifier = candidate["id"]
            if identifier not in merged:
                merged[identifier] = dict(candidate)
                continue
            current = merged[identifier]
            seen_in = set(current.get("seen_in", []))
            seen_in.update(candidate.get("seen_in", []))
            current_has_target = bool(current.get("target"))
            candidate_has_target = bool(candidate.get("target"))
            if candidate_has_target or not current_has_target:
                replacement = dict(candidate)
                replacement["seen_in"] = sorted(
                    seen_in,
                    key=lambda value: (
                        value.split("@", maxsplit=1)[0],
                        semver_key(value.split("@", maxsplit=1)[1]),
                    ),
                )
                merged[identifier] = replacement
            else:
                current["seen_in"] = sorted(
                    seen_in,
                    key=lambda value: (
                        value.split("@", maxsplit=1)[0],
                        semver_key(value.split("@", maxsplit=1)[1]),
                    ),
                )
    latest = corpora[-1]
    return {
        "format_version": latest.get("format_version", "1.0.0"),
        "target": target,
        "version": latest["version"],
        "generated_at": latest["generated_at"],
        "units": sorted(merged.values(), key=lambda unit: unit["id"]),
    }


def _fetch_npm_latest(timeout: float = 30.0) -> str:
    request = urllib.request.Request(
        NPM_LATEST_URL,
        headers={"Accept": "application/json", "User-Agent": "claude-zh-pipeline/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    version = payload.get("version") if isinstance(payload, dict) else None
    if not isinstance(version, str):
        raise ValueError("npm latest response has no version")
    semver_key(version)
    return version


def parse_desktop_version(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        matches = _SEMVER.findall(value)
        if matches:
            return max(matches, key=semver_key)
    return None


def _fetch_desktop_latest(timeout: float = 30.0) -> str:
    request = urllib.request.Request(
        DESKTOP_LATEST_URL,
        method="GET",
        headers={"User-Agent": "Mozilla/5.0 claude-zh-pipeline/1"},
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        if error.code not in {301, 302, 303, 307, 308}:
            raise
        version = parse_desktop_version(
            error.headers.get("Location"),
            error.headers.get("Content-Disposition"),
        )
    else:
        with response:
            version = parse_desktop_version(
                response.headers.get("Location"),
                response.headers.get("Content-Disposition"),
                response.geturl(),
            )
    if version is None:
        raise ValueError("official Desktop response does not expose a version")
    return version


def _target_detection(
    target: str,
    latest: str | None,
    error: str | None,
    source_url: str,
    corpus_root: Path,
) -> dict[str, Any]:
    known = known_versions(target, corpus_root)
    newest_known = known[-1] if known else None
    new_available = bool(
        latest
        and (
            newest_known is None
            or semver_key(latest) > semver_key(newest_known)
        )
    )
    return {
        "source": source_url,
        "status": "available" if latest else "unavailable",
        "latest": latest,
        "known": known,
        "newest_known": newest_known,
        "new_available": new_available,
        "error": error,
    }


def detect_versions(corpus_root: Path = ROOT / "corpus") -> dict[str, Any]:
    cli_version: str | None = None
    cli_error: str | None = None
    desktop_version: str | None = None
    desktop_error: str | None = None
    try:
        cli_version = _fetch_npm_latest()
    except (OSError, ValueError, urllib.error.URLError) as error:
        cli_error = f"{type(error).__name__}: {error}"
    try:
        desktop_version = _fetch_desktop_latest()
    except (OSError, ValueError, urllib.error.URLError) as error:
        desktop_error = f"{type(error).__name__}: {error}"
    return {
        "checked_at": utc_now(),
        "cli": _target_detection(
            "cli",
            cli_version,
            cli_error,
            NPM_LATEST_URL,
            corpus_root,
        ),
        "desktop": _target_detection(
            "desktop",
            desktop_version,
            desktop_error,
            DESKTOP_LATEST_URL,
            corpus_root,
        ),
    }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as destination:
        json.dump(value, destination, ensure_ascii=False, indent=2)
        destination.write("\n")


def _npm_pack(package: str, destination: Path) -> Path:
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm executable not found")
    destination.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            npm,
            "pack",
            package,
            "--ignore-scripts",
            "--pack-destination",
            str(destination.resolve()),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"npm pack failed for {package}: {detail}")
    try:
        payload = json.loads(result.stdout)
        filename = payload[0]["filename"]
    except (json.JSONDecodeError, IndexError, KeyError, TypeError) as error:
        raise RuntimeError(f"unexpected npm pack output for {package}") from error
    archive = (destination / filename).resolve()
    if archive.parent != destination.resolve() or archive.suffix != ".tgz":
        raise RuntimeError(f"npm returned an unsafe archive path: {filename}")
    if not archive.is_file():
        raise RuntimeError(f"npm archive is missing: {archive}")
    return archive


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive, mode="r:gz") as package:
        for member in package.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts:
                raise RuntimeError(f"unsafe archive member: {member.name}")
            output = root.joinpath(*name.parts)
            if not output.resolve().is_relative_to(root):
                raise RuntimeError(f"archive member escapes destination: {member.name}")
            if member.isdir():
                output.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise RuntimeError(f"unsupported archive member: {member.name}")
            output.parent.mkdir(parents=True, exist_ok=True)
            extracted = package.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"cannot read archive member: {member.name}")
            with extracted, output.open("wb") as destination_file:
                shutil.copyfileobj(extracted, destination_file)


def _platform_package(optional: dict[str, Any]) -> str:
    system = {
        "linux": "linux",
        "darwin": "darwin",
        "win32": "win32",
    }.get(sys.platform)
    machine = platform.machine().casefold()
    architecture = (
        "arm64"
        if machine in {"arm64", "aarch64"}
        else "x64"
        if machine in {"amd64", "x86_64"}
        else None
    )
    if system is None or architecture is None:
        raise RuntimeError(f"unsupported runner platform: {sys.platform}/{machine}")
    prefix = f"@anthropic-ai/claude-code-{system}-{architecture}"
    matches = sorted(name for name in optional if name == prefix)
    if not matches:
        raise RuntimeError(f"upstream package has no dependency for {prefix}")
    return matches[0]


def _find_native_artifact(package_root: Path) -> Path:
    files = [path for path in package_root.rglob("*") if path.is_file()]
    preferred = [
        path
        for path in files
        if path.name.casefold() in {"claude", "claude.exe"}
    ]
    candidates = preferred or [
        path
        for path in files
        if path.suffix.casefold() not in {".json", ".md", ".txt"}
        and path.stat().st_size >= 1024 * 1024
    ]
    if not candidates:
        raise RuntimeError("native Claude artifact not found in platform package")
    return max(candidates, key=lambda path: path.stat().st_size)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_cli(version: str, work_directory: Path) -> dict[str, Any]:
    """Download with npm pack and extract without installing any package."""
    semver_key(version)
    downloads = work_directory / "downloads"
    main_archive = _npm_pack(
        f"@anthropic-ai/claude-code@{version}",
        downloads,
    )
    main_root = work_directory / "main"
    _safe_extract(main_archive, main_root)
    package_root = main_root / "package"
    cli_js = package_root / "cli.js"
    archives = [main_archive]
    package_name = "@anthropic-ai/claude-code"
    if cli_js.is_file():
        artifact = cli_js
        artifact_type = "javascript"
    else:
        with (package_root / "package.json").open("r", encoding="utf-8") as source:
            package_json = json.load(source)
        optional = package_json.get("optionalDependencies") or {}
        if not isinstance(optional, dict):
            raise RuntimeError("upstream optionalDependencies must be an object")
        package_name = _platform_package(optional)
        package_version = optional[package_name]
        if package_version != version:
            raise RuntimeError(
                f"platform package version mismatch: {package_version} != {version}"
            )
        native_archive = _npm_pack(f"{package_name}@{version}", downloads)
        archives.append(native_archive)
        native_root = work_directory / "native"
        _safe_extract(native_archive, native_root)
        artifact = _find_native_artifact(native_root / "package")
        artifact_type = "binary"
    digest = _sha256(artifact)
    return {
        "version": version,
        "package": package_name,
        "artifact": str(artifact.resolve()),
        "artifact_type": artifact_type,
        "artifact_sha256": digest,
        "archives": [str(path.resolve()) for path in archives],
    }


def extract_cli(
    prepared: dict[str, Any],
    output: Path,
) -> int:
    artifact = Path(prepared["artifact"])
    version = prepared["version"]
    if prepared["artifact_type"] == "javascript":
        command = [
            sys.executable,
            str(ROOT / "extractors" / "js-ast" / "extract.py"),
            str(artifact),
            "cli",
            version,
            str(output),
        ]
    elif prepared["artifact_type"] == "binary":
        command = [
            sys.executable,
            str(ROOT / "extractors" / "binary" / "extract.py"),
            str(artifact),
            "cli",
            version,
            str(output),
        ]
    else:
        raise RuntimeError(f"unknown artifact type: {prepared['artifact_type']}")
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"extractor failed: {detail}")
    try:
        return int(json.loads(result.stdout)["extracted"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise RuntimeError("extractor returned an invalid count") from error


def run_cli_update(
    old_corpus: dict[str, Any],
    version: str,
    work_directory: Path,
    generated_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    prepared = prepare_cli(version, work_directory)
    extracted = work_directory / "extracted.jsonl"
    extracted_count = extract_cli(prepared, extracted)
    corpus, report = inherit_corpus(
        old_corpus,
        read_jsonl([extracted]),
        "cli",
        version,
        generated_at,
    )
    report["extracted"] = extracted_count
    report["artifact_type"] = prepared["artifact_type"]
    report["artifact_sha256"] = prepared["artifact_sha256"]
    report["package"] = prepared["package"]
    return corpus, report


def _empty_corpus(version: str, generated_at: str) -> dict[str, Any]:
    return {
        "format_version": "1.0.0",
        "target": "cli",
        "version": version,
        "generated_at": generated_at,
        "units": [],
    }


def run_historical_drill(
    old_version: str,
    new_version: str,
    work_directory: Path,
) -> dict[str, Any]:
    generated_at = utc_now()
    old_corpus, old_report = run_cli_update(
        _empty_corpus(old_version, generated_at),
        old_version,
        work_directory / old_version,
        generated_at,
    )
    new_corpus, new_report = run_cli_update(
        old_corpus,
        new_version,
        work_directory / new_version,
        generated_at,
    )
    omitted_detail_keys = {
        "alerts",
        "new_ids",
        "new_ids_truncated",
        "disappeared_ids",
        "disappeared_ids_truncated",
    }
    old_summary = {
        key: value
        for key, value in old_report.items()
        if key not in omitted_detail_keys
    }
    new_summary = {
        key: value
        for key, value in new_report.items()
        if key not in omitted_detail_keys
    }
    return {
        "checked_at": generated_at,
        "old_version": old_version,
        "new_version": new_version,
        "old_units": len(old_corpus["units"]),
        "new_units": len(
            [unit for unit in new_corpus["units"] if not unit["deprecated"]]
        ),
        "old_report": old_summary,
        "new_report": new_summary,
        "passed": new_report["inheritance_rate"] > 0.85,
        "threshold": 0.85,
    }


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def _command_detect(args: argparse.Namespace) -> int:
    result = detect_versions(args.corpus_root)
    _write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _command_prepare(args: argparse.Namespace) -> int:
    result = prepare_cli(args.version, args.work_directory)
    _write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _command_merge_base(args: argparse.Namespace) -> int:
    result = merge_corpus_history(args.target, args.corpus_root)
    _write_json(args.output, result)
    print(
        json.dumps(
            {
                "target": result["target"],
                "version": result["version"],
                "units": len(result["units"]),
            }
        )
    )
    return 0


def _command_inherit(args: argparse.Namespace) -> int:
    old_corpus = _load_json(args.old_corpus)
    corpus, report = inherit_corpus(
        old_corpus,
        read_jsonl(args.inputs),
        args.target,
        args.version,
        args.generated_at or utc_now(),
    )
    _write_json(args.output_corpus, corpus)
    _write_json(args.output_report, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


def _command_update_cli(args: argparse.Namespace) -> int:
    old_corpus = _load_json(args.old_corpus)
    corpus, report = run_cli_update(
        old_corpus,
        args.version,
        args.work_directory,
        args.generated_at or utc_now(),
    )
    _write_json(args.output_corpus, corpus)
    _write_json(args.output_report, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0


def _command_drill(args: argparse.Namespace) -> int:
    result = run_historical_drill(
        args.old_version,
        args.new_version,
        args.work_directory,
    )
    _write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


def _command_gate_update(args: argparse.Namespace) -> int:
    report = _load_json(args.report)
    rate = report.get("inheritance_rate")
    if not isinstance(rate, (int, float)):
        print("update gate failed: report has no inheritance_rate", file=sys.stderr)
        return 1
    if rate < args.minimum:
        print(
            (
                f"update gate failed: inheritance rate {rate:.2%} is below "
                f"{args.minimum:.2%}; upstream structure requires manual review"
            ),
            file=sys.stderr,
        )
        return 1
    print(f"update gate passed: inheritance rate {rate:.2%}")
    return 0


def _command_pr_body(args: argparse.Namespace) -> int:
    report = _load_json(args.report)
    low_confidence: list[dict[str, Any]] = []
    if args.suggestions and args.suggestions.is_file():
        suggestions = _load_json(args.suggestions)
        items = suggestions.get("items", []) if isinstance(suggestions, dict) else []
        low_confidence = [
            item
            for item in items
            if isinstance(item, dict)
            and isinstance(item.get("confidence"), (int, float))
            and item["confidence"] < 0.8
        ]
    body = render_pr_body(report, low_confidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(body, encoding="utf-8", newline="\n")
    print(f"wrote {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    detect = commands.add_parser("detect")
    detect.add_argument("output", type=Path)
    detect.add_argument("--corpus-root", type=Path, default=ROOT / "corpus")
    detect.set_defaults(handler=_command_detect)

    prepare = commands.add_parser("prepare-cli")
    prepare.add_argument("version")
    prepare.add_argument("work_directory", type=Path)
    prepare.add_argument("output", type=Path)
    prepare.set_defaults(handler=_command_prepare)

    merge_base = commands.add_parser("merge-base")
    merge_base.add_argument("target", choices=("cli", "desktop"))
    merge_base.add_argument("output", type=Path)
    merge_base.add_argument("--corpus-root", type=Path, default=ROOT / "corpus")
    merge_base.set_defaults(handler=_command_merge_base)

    inherit = commands.add_parser("inherit")
    inherit.add_argument("target", choices=("cli", "desktop"))
    inherit.add_argument("version")
    inherit.add_argument("old_corpus", type=Path)
    inherit.add_argument("output_corpus", type=Path)
    inherit.add_argument("output_report", type=Path)
    inherit.add_argument("inputs", nargs="+", type=Path)
    inherit.add_argument("--generated-at")
    inherit.set_defaults(handler=_command_inherit)

    update_cli = commands.add_parser("update-cli")
    update_cli.add_argument("version")
    update_cli.add_argument("old_corpus", type=Path)
    update_cli.add_argument("work_directory", type=Path)
    update_cli.add_argument("output_corpus", type=Path)
    update_cli.add_argument("output_report", type=Path)
    update_cli.add_argument("--generated-at")
    update_cli.set_defaults(handler=_command_update_cli)

    drill = commands.add_parser("historical-drill")
    drill.add_argument("output", type=Path)
    drill.add_argument("work_directory", type=Path)
    drill.add_argument("--old-version", default="2.1.111")
    drill.add_argument("--new-version", default="2.1.112")
    drill.set_defaults(handler=_command_drill)

    gate_update = commands.add_parser("gate-update")
    gate_update.add_argument("report", type=Path)
    gate_update.add_argument("--minimum", type=float, default=0.8)
    gate_update.set_defaults(handler=_command_gate_update)

    pr_body = commands.add_parser("pr-body")
    pr_body.add_argument("report", type=Path)
    pr_body.add_argument("output", type=Path)
    pr_body.add_argument("--suggestions", type=Path)
    pr_body.set_defaults(handler=_command_pr_body)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except (
        OSError,
        ValueError,
        RuntimeError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        tarfile.TarError,
    ) as error:
        print(f"pipeline failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
