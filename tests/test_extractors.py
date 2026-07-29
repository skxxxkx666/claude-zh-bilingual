from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "extractor_sample.js"


class ExtractorIntegrationTests(unittest.TestCase):
    def test_locale_extractor_emits_ui_context(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "locale_sample.json"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "locale.jsonl"
            subprocess.run(
                [
                    sys.executable,
                    str(
                        ROOT
                        / "extractors"
                        / "locale-json"
                        / "extract.py"
                    ),
                    str(fixture),
                    "desktop",
                    "0.0.0",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            records = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(records), 2)
        self.assertTrue(
            all(
                record["context"]["source_kind"] == "locale"
                for record in records
            )
        )

    def test_binary_extractor_emits_offsets_and_lengths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "binary.jsonl"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "extractors" / "binary" / "extract.py"),
                    str(FIXTURE),
                    "cli",
                    "0.0.0",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            records = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
            ]

        self.assertGreater(len(records), 0)
        self.assertTrue(
            all(record["offset_unit"] == "byte" for record in records)
        )
        self.assertTrue(all(record["byte_length"] > 0 for record in records))

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_js_ast_extractor_and_classifier_pipeline(self) -> None:
        acorn = ROOT / "node_modules" / "acorn" / "dist" / "acorn.js"
        if not acorn.is_file():
            self.skipTest("run npm ci to install Acorn")

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            extracted = work / "ast.jsonl"
            queues = work / "queues"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "extractors" / "js-ast" / "extract.py"),
                    str(FIXTURE.parent),
                    "cli",
                    "0.0.0",
                    str(extracted),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "classifiers" / "classify.py"),
                    str(extracted),
                    str(queues),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            excluded = [
                json.loads(line)
                for line in (queues / "excluded.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            candidates = [
                json.loads(line)
                for line in (queues / "candidates.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            extracted_records = [
                json.loads(line)
                for line in extracted.read_text(encoding="utf-8").splitlines()
            ]

        reasons = {record["risk_reason"] for record in excluded}
        self.assertIn("R-TOOLDESC", reasons)
        self.assertIn("R-CODEMATCH", reasons)
        self.assertTrue(all(record["risk"] != "SAFE" for record in candidates))
        self.assertIn(
            "Loaded ${button}",
            {record["source"] for record in extracted_records},
        )


if __name__ == "__main__":
    unittest.main()
