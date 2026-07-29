from __future__ import annotations

import io
import json
import tarfile
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from scripts.update_pipeline import (
    _command_gate_update,
    _safe_extract,
    known_versions,
    merge_corpus_history,
    parse_desktop_version,
    semver_key,
)


class UpdatePipelineTests(unittest.TestCase):
    def test_semver_sort_is_numeric(self) -> None:
        values = ["2.1.9", "2.1.112", "2.10.0"]
        self.assertEqual(
            sorted(values, key=semver_key),
            ["2.1.9", "2.1.112", "2.10.0"],
        )

    def test_desktop_version_comes_from_official_redirect_metadata(self) -> None:
        self.assertEqual(
            parse_desktop_version(
                "https://downloads.claude.ai/releases/1.2581.0/Claude.exe",
                'attachment; filename="Claude-1.2581.0.exe"',
            ),
            "1.2581.0",
        )
        self.assertIsNone(parse_desktop_version("https://claude.ai/download"))

    def test_known_versions_ignores_non_semver_layer_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus_root = Path(directory)
            target = corpus_root / "cli"
            target.mkdir()
            (target / "2.1.9.json").write_text(
                json.dumps({"version": "2.1.9"}),
                encoding="utf-8",
            )
            (target / "2.1.112.json").write_text(
                json.dumps({"version": "2.1.112"}),
                encoding="utf-8",
            )
            (target / "layer-a.json").write_text(
                json.dumps({"version": "layer-a"}),
                encoding="utf-8",
            )

            self.assertEqual(
                known_versions("cli", corpus_root),
                ["2.1.9", "2.1.112"],
            )

    def test_merge_history_keeps_older_units_and_prefers_translation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus_root = Path(directory)
            target = corpus_root / "cli"
            target.mkdir()
            older = {
                "format_version": "1.0.0",
                "target": "cli",
                "version": "2.1.112",
                "generated_at": "2026-07-29T00:00:00Z",
                "units": [
                    {
                        "id": "0000000000000001",
                        "source": "Older only",
                        "target": None,
                        "seen_in": ["cli@2.1.112"],
                    },
                    {
                        "id": "0000000000000002",
                        "source": "Shared",
                        "target": None,
                        "seen_in": ["cli@2.1.112"],
                    },
                ],
            }
            newer = {
                "format_version": "1.0.0",
                "target": "cli",
                "version": "2.1.201",
                "generated_at": "2026-07-30T00:00:00Z",
                "units": [
                    {
                        "id": "0000000000000002",
                        "source": "Shared",
                        "target": "共享",
                        "seen_in": ["cli@2.1.201"],
                    }
                ],
            }
            (target / "full.json").write_text(
                json.dumps(older),
                encoding="utf-8",
            )
            (target / "layer-a.json").write_text(
                json.dumps(newer),
                encoding="utf-8",
            )

            merged = merge_corpus_history("cli", corpus_root)

        self.assertEqual(merged["version"], "2.1.201")
        self.assertEqual(len(merged["units"]), 2)
        shared = next(
            unit
            for unit in merged["units"]
            if unit["id"] == "0000000000000002"
        )
        self.assertEqual(shared["target"], "共享")
        self.assertEqual(
            shared["seen_in"],
            ["cli@2.1.112", "cli@2.1.201"],
        )

    def test_safe_extract_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bad.tgz"
            with tarfile.open(archive, "w:gz") as package:
                content = b"blocked"
                member = tarfile.TarInfo("../escape.txt")
                member.size = len(content)
                package.addfile(member, io.BytesIO(content))

            with self.assertRaisesRegex(RuntimeError, "unsafe archive member"):
                _safe_extract(archive, root / "output")
            self.assertFalse((root / "escape.txt").exists())

    def test_safe_extract_writes_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "good.tgz"
            with tarfile.open(archive, "w:gz") as package:
                content = b"ok"
                member = tarfile.TarInfo("package/file.txt")
                member.size = len(content)
                package.addfile(member, io.BytesIO(content))

            _safe_extract(archive, root / "output")
            self.assertEqual(
                (root / "output" / "package" / "file.txt").read_bytes(),
                b"ok",
            )

    def test_update_gate_blocks_structural_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            report.write_text(
                json.dumps({"inheritance_rate": 0.79}),
                encoding="utf-8",
            )
            result = _command_gate_update(
                Namespace(report=report, minimum=0.8)
            )
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
