#!/usr/bin/env python3
"""Generate the support matrix and enforce the release smoke-test gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release" / "desktop-v0.1.0.json"
OUTPUT = ROOT / "docs" / "support-matrix.md"
PACKAGE = ROOT / "package.json"
CORPUS_ROOT = ROOT / "corpus"
LAST_JS_CLI_VERSION = "2.1.112"

STATUS_LABELS = {
    "supported": "支持",
    "candidate": "候选",
    "unsupported": "不支持",
}


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def _cell(value: object) -> str:
    return str(value).replace("|", r"\|").replace("\n", " ")


def _semver_key(value: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


def corpus_lifecycle(corpus_root: Path = CORPUS_ROOT) -> list[dict[str, str]]:
    versions: dict[str, set[str]] = {"cli": set(), "desktop": set()}
    for target in versions:
        for path in (corpus_root / target).glob("*.json"):
            try:
                data = _read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            version = data.get("version") if isinstance(data, dict) else None
            if (
                isinstance(version, str)
                and len(version.split(".")) == 3
                and all(part.isdigit() for part in version.split("."))
            ):
                versions[target].add(version)

    rows: list[dict[str, str]] = []
    for target, target_versions in versions.items():
        minor_versions = sorted(
            {(key[0], key[1]) for key in map(_semver_key, target_versions)}
        )
        supported_minors = set(minor_versions[-3:])
        for version in sorted(target_versions, key=_semver_key, reverse=True):
            key = _semver_key(version)
            last_js = target == "cli" and version == LAST_JS_CLI_VERSION
            supported = (key[0], key[1]) in supported_minors or last_js
            if last_js:
                reason = "最后一个 JS 版本，长期保留"
            elif supported:
                reason = "最近 3 个 minor 版本"
            else:
                reason = "超出最近 3 个 minor 版本"
            rows.append(
                {
                    "target": target,
                    "version": version,
                    "lifecycle": "supported" if supported else "eol",
                    "reason": reason,
                }
            )
    return rows


def render_support_matrix(
    manifest: dict[str, Any],
    corpus_root: Path = CORPUS_ROOT,
) -> str:
    release_state = "可发布" if manifest["release_ready"] else "禁止发布"
    lines = [
        "# 支持矩阵",
        "",
        "> 此文件由 `python scripts/release_status.py --write` 生成，"
        "数据源是 `release/desktop-v0.1.0.json`，不要手工修改。",
        "",
        f"## {manifest['release']} 状态",
        "",
        f"当前门禁：**{release_state}**。",
        "",
        "| 断言 | 状态 | 证据 |",
        "|---|---|---|",
    ]
    for assertion, result in manifest["smoke"].items():
        lines.append(
            f"| {_cell(assertion)} | {_cell(result['status'])} | "
            f"{_cell(result['evidence'])} |"
        )

    lines.extend(
        [
            "",
            "## 平台与版本",
            "",
            "| 平台 | 安装类型 | Claude Desktop | 状态 | 说明 |",
            "|---|---|---|---|---|",
        ]
    )
    for entry in manifest["support"]:
        lines.append(
            f"| {_cell(entry['platform'])} | {_cell(entry['install_type'])} | "
            f"{_cell(entry['desktop_version'])} | "
            f"{_cell(STATUS_LABELS[entry['status']])} | {_cell(entry['notes'])} |"
        )

    lines.extend(
        [
            "",
            "## 语料版本生命周期",
            "",
            "> 支持范围：最近 3 个 minor 版本，以及最后一个 JS 版本 "
            f"`cli@{LAST_JS_CLI_VERSION}`。超出范围的版本保留语料但标记 EOL。",
            "",
            "| 目标 | 版本 | 生命周期 | 原因 |",
            "|---|---|---|---|",
        ]
    )
    for entry in corpus_lifecycle(corpus_root):
        lifecycle = "支持范围" if entry["lifecycle"] == "supported" else "EOL"
        lines.append(
            f"| {_cell(entry['target'])} | {_cell(entry['version'])} | "
            f"{lifecycle} | {_cell(entry['reason'])} |"
        )

    lines.extend(
        [
            "",
            "## 安装与还原",
            "",
            "从 GitHub Release 下载 `claude-zh-0.1.0.tgz` 后，在空目录执行：",
            "",
            "```powershell",
            "npm install .\\claude-zh-0.1.0.tgz",
            "npx claude-zh status",
            "npx claude-zh install desktop --mode=zh",
            "npx claude-zh restore desktop",
            "```",
            "",
            "安装和还原前都要正常退出 Claude。补丁器不会结束进程，"
            "会在改动前打印并校验应用目录之外的备份路径；"
            "还原完成后逐文件核对原始 SHA-256。",
            "",
            "MSIX 安装只返回 `msix-unsupported`，不写入 `WindowsApps`。"
            "macOS 当前不支持。",
            "",
        ]
    )
    return "\n".join(lines)


def release_gate_errors(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    package = _read_json(PACKAGE)
    corpus = _read_json(
        CORPUS_ROOT / "desktop" / f"{manifest['corpus']['version']}.json"
    )

    if manifest["release"] != f"v{manifest['package_version']}":
        errors.append("release tag does not match manifest package_version")
    if package["version"] != manifest["package_version"]:
        errors.append("package.json version does not match release manifest")
    if not manifest["release_ready"]:
        errors.append("release_ready is false")

    incomplete = [
        assertion
        for assertion, result in manifest["smoke"].items()
        if result["status"] != "pass"
    ]
    if incomplete:
        errors.append(f"smoke assertions are not passing: {', '.join(incomplete)}")

    if not any(entry["status"] == "supported" for entry in manifest["support"]):
        errors.append("support matrix has no supported target")

    expected_version = manifest["corpus"]["version"]
    expected_verification = manifest["corpus"]["verified_at"]
    if corpus.get("target") != "desktop" or corpus.get("version") != expected_version:
        errors.append("Desktop corpus does not match the release manifest")
    unverified = [
        unit["id"]
        for unit in corpus.get("units", [])
        if unit.get("risk") == "SAFE"
        and unit.get("verified_at") != expected_verification
    ]
    if unverified:
        errors.append(f"{len(unverified)} SAFE corpus units are not smoke-verified")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--write", action="store_true")
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--release-gate", action="store_true")
    args = parser.parse_args()

    manifest = _read_json(MANIFEST)
    rendered = render_support_matrix(manifest)
    if args.write:
        OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
        return 0
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            print(
                "support matrix is stale; run "
                "python scripts/release_status.py --write",
                file=sys.stderr,
            )
            return 1
        print("support matrix is current")
        return 0

    errors = release_gate_errors(manifest)
    if errors:
        for error in errors:
            print(f"release blocked: {error}", file=sys.stderr)
        return 1
    print(f"release gate passed for {manifest['release']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
