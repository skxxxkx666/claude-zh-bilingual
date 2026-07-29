from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.release_status import (
    LAST_JS_CLI_VERSION,
    corpus_lifecycle,
    current_manifest_path,
    release_gate_errors,
    render_support_matrix,
)


class ReleaseStatusTests(unittest.TestCase):
    def test_manifest_path_follows_package_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package_path = Path(directory) / "package.json"
            package_path.write_text(
                json.dumps({"version": "0.2.0-rc.1"}),
                encoding="utf-8",
            )

            manifest_path = current_manifest_path(package_path)

        self.assertEqual(manifest_path.name, "desktop-v0.2.0-rc.1.json")

    def test_lifecycle_keeps_three_minors_and_last_js_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus_root = Path(directory)
            for target in ("cli", "desktop"):
                (corpus_root / target).mkdir()
            cli_versions = [
                LAST_JS_CLI_VERSION,
                "2.2.1",
                "2.3.1",
                "2.4.1",
                "2.5.1",
            ]
            for version in cli_versions:
                (corpus_root / "cli" / f"{version}.json").write_text(
                    json.dumps({"target": "cli", "version": version}),
                    encoding="utf-8",
                )
            (corpus_root / "desktop" / "1.100.0.json").write_text(
                json.dumps({"target": "desktop", "version": "1.100.0"}),
                encoding="utf-8",
            )

            rows = corpus_lifecycle(corpus_root)

        by_version = {
            (row["target"], row["version"]): row["lifecycle"] for row in rows
        }
        self.assertEqual(by_version[("cli", LAST_JS_CLI_VERSION)], "supported")
        self.assertEqual(by_version[("cli", "2.2.1")], "eol")
        self.assertEqual(by_version[("cli", "2.3.1")], "supported")
        self.assertEqual(by_version[("cli", "2.5.1")], "supported")
        self.assertEqual(by_version[("desktop", "1.100.0")], "supported")

    def test_prerelease_matrix_warns_about_unsigned_launcher(self) -> None:
        manifest = {
            "release": "v0.2.0-rc.1",
            "package_version": "0.2.0-rc.1",
            "release_channel": "prerelease",
            "release_ready": True,
            "smoke": {},
            "support": [],
            "launcher": {
                "platform": "Windows x64",
                "artifact": "claude-zh-windows-x64.exe",
                "node_version": "22.23.1",
                "signed": False,
                "smoke": {},
            },
        }

        rendered = render_support_matrix(manifest)

        self.assertIn("SmartScreen", rendered)
        self.assertIn("未做 Authenticode 代码签名", rendered)
        self.assertIn("claude-zh-0.2.0-rc.1.tgz", rendered)
        self.assertIn("候选可发布", rendered)

    def test_unsigned_launcher_is_blocked_from_stable_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_path = root / "package.json"
            corpus_root = root / "corpus"
            (corpus_root / "desktop").mkdir(parents=True)
            package_path.write_text(
                json.dumps({"version": "0.2.0"}),
                encoding="utf-8",
            )
            (corpus_root / "desktop" / "1.0.0.json").write_text(
                json.dumps(
                    {
                        "target": "desktop",
                        "version": "1.0.0",
                        "units": [],
                    }
                ),
                encoding="utf-8",
            )
            manifest = {
                "release": "v0.2.0",
                "package_version": "0.2.0",
                "release_channel": "stable",
                "release_ready": True,
                "corpus": {"version": "1.0.0", "verified_at": "desktop@1.0.0"},
                "smoke": {
                    assertion: {"status": "pass"}
                    for assertion in ("D1", "D2", "D3", "D4")
                },
                "support": [{"status": "supported"}],
                "launcher": {
                    "status": "candidate",
                    "platform": "Windows x64",
                    "artifact": "claude-zh-windows-x64.exe",
                    "node_version": "22.23.1",
                    "signed": False,
                    "smoke": {
                        "embedded_cli": {"status": "pass"},
                        "conpty": {"status": "pass"},
                    },
                },
            }

            errors = release_gate_errors(manifest, package_path, corpus_root)

        self.assertIn("unsigned launcher is allowed only in a prerelease", errors)


if __name__ == "__main__":
    unittest.main()
