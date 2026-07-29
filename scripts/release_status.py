#!/usr/bin/env python3
"""Generate the support matrix and enforce the release smoke-test gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
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


def current_manifest_path(package_path: Path = PACKAGE) -> Path:
    package = _read_json(package_path)
    return ROOT / "release" / f"desktop-v{package['version']}.json"


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
    manifest_path: Path | None = None,
) -> str:
    release_channel = manifest.get("release_channel", "stable")
    if manifest["release_ready"]:
        release_state = (
            "候选可发布" if release_channel == "prerelease" else "可发布"
        )
    else:
        release_state = "禁止发布"
    manifest_path = manifest_path or (
        ROOT / "release" / f"desktop-v{manifest['package_version']}.json"
    )
    package_filename = f"claude-zh-{manifest['package_version']}.tgz"
    lines = [
        "# 支持矩阵",
        "",
        "> 此文件由 `python scripts/release_status.py --write` 生成，"
        f"数据源是 `{manifest_path.relative_to(ROOT).as_posix()}`，不要手工修改。",
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

    launcher = manifest.get("launcher")
    if launcher:
        signature = "已签名" if launcher["signed"] else "未签名"
        lines.extend(
            [
                "",
                "## Windows 单文件启动器（预发布）",
                "",
                "> **SmartScreen 提示：** "
                "此候选 EXE 未做 Authenticode 代码签名，Windows 可能显示"
                "“Windows 已保护你的电脑”。只从本仓库的 GitHub Release 下载，"
                "并在运行前核对 SHA-256；无法确认来源或哈希不一致时不要运行。",
                "",
                "| 项目 | 值 |",
                "|---|---|",
                f"| 平台 | {_cell(launcher['platform'])} |",
                f"| 文件 | `{_cell(launcher['artifact'])}` |",
                f"| 内置 Node | `{_cell(launcher['node_version'])}` |",
                f"| Authenticode | {signature} |",
            ]
        )
        for assertion, result in launcher["smoke"].items():
            lines.append(
                f"| {_cell(assertion)} | {_cell(result['status'])}："
                f"{_cell(result['evidence'])} |"
            )
        lines.extend(
            [
                "",
                "下载同一 Release 中的 EXE 与 `SHA256SUMS.windows`，然后核对：",
                "",
                "```powershell",
                "(Get-FileHash .\\claude-zh-windows-x64.exe "
                "-Algorithm SHA256).Hash.ToLowerInvariant()",
                "Get-Content .\\SHA256SUMS.windows",
                "```",
                "",
                "两处哈希必须完全一致。确认后双击 EXE，按中文菜单执行安装、"
                "状态检查或还原。此候选版不替代稳定版 `v0.1.0`。",
            ]
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
            f"从 GitHub Release 下载 `{package_filename}` 后，在空目录执行：",
            "",
            "```powershell",
            f"npm install .\\{package_filename}",
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


def release_gate_errors(
    manifest: dict[str, Any],
    package_path: Path = PACKAGE,
    corpus_root: Path = CORPUS_ROOT,
) -> list[str]:
    errors: list[str] = []
    package = _read_json(package_path)
    corpus = _read_json(
        corpus_root / "desktop" / f"{manifest['corpus']['version']}.json"
    )
    package_version = manifest["package_version"]
    release_channel = manifest.get("release_channel", "stable")

    if manifest["release"] != f"v{package_version}":
        errors.append("release tag does not match manifest package_version")
    if package["version"] != package_version:
        errors.append("package.json version does not match release manifest")
    if not manifest["release_ready"]:
        errors.append("release_ready is false")
    if release_channel not in {"stable", "prerelease"}:
        errors.append("release_channel must be stable or prerelease")
    elif ("-" in package_version) != (release_channel == "prerelease"):
        errors.append("release_channel does not match package prerelease version")

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

    launcher = manifest.get("launcher")
    if launcher:
        if launcher.get("status") != "candidate":
            errors.append("launcher status must be candidate")
        if launcher.get("artifact") != "claude-zh-windows-x64.exe":
            errors.append("launcher artifact name is not approved")
        if launcher.get("platform") != "Windows x64":
            errors.append("launcher platform must be Windows x64")
        if launcher.get("node_version") != "22.23.1":
            errors.append("launcher Node version is not pinned to 22.23.1")
        if not isinstance(launcher.get("signed"), bool):
            errors.append("launcher signed state must be explicit")
        elif not launcher["signed"] and release_channel != "prerelease":
            errors.append("unsigned launcher is allowed only in a prerelease")
        launcher_smoke = launcher.get("smoke", {})
        required_launcher_smoke = {"embedded_cli", "conpty"}
        if set(launcher_smoke) != required_launcher_smoke or any(
            result.get("status") != "pass" for result in launcher_smoke.values()
        ):
            errors.append("launcher embedded CLI and ConPTY smoke tests must pass")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--write", action="store_true")
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--release-gate", action="store_true")
    args = parser.parse_args()

    manifest_path = current_manifest_path()
    manifest = _read_json(manifest_path)
    rendered = render_support_matrix(manifest, manifest_path=manifest_path)
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
