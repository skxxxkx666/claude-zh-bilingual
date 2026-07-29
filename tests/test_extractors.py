from __future__ import annotations

import json
import hashlib
import shutil
import struct
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

    def test_binary_extractor_applies_reviewed_bun_surface_map(self) -> None:
        source_text = "Display help text"
        source_bytes = source_text.encode("ascii")
        pe_offset = 0x80
        raw_start = 0x200
        record_bytes = struct.pack("<II", 9, len(source_bytes)) + source_bytes
        payload = record_bytes + b"\0" + record_bytes
        binary = bytearray(raw_start + len(payload))
        binary[:2] = b"MZ"
        struct.pack_into("<I", binary, 0x3C, pe_offset)
        binary[pe_offset : pe_offset + 4] = b"PE\0\0"
        struct.pack_into("<H", binary, pe_offset + 6, 1)
        struct.pack_into("<H", binary, pe_offset + 20, 0)
        section = pe_offset + 24
        binary[section : section + 8] = b".bun\0\0\0\0"
        struct.pack_into(
            "<IIII",
            binary,
            section + 8,
            len(payload),
            0x1000,
            len(payload),
            raw_start,
        )
        struct.pack_into("<I", binary, section + 36, 0x40000040)
        binary[raw_start:] = payload

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary_path = root / "claude.exe"
            output = root / "binary.jsonl"
            surface_map = root / "surface-map.json"
            binary_path.write_bytes(binary)
            surface_map.write_text(
                json.dumps(
                    {
                        "target": "cli",
                        "version": "2.1.220",
                        "artifact_sha256": hashlib.sha256(binary).hexdigest(),
                        "approved": [
                            {
                                "source": source_text,
                                "surface": "cli.help",
                                "occurrences": [raw_start + 8],
                                "decision": "APPROVED",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "extractors" / "binary" / "extract.py"),
                    str(binary_path),
                    "cli",
                    "2.1.220",
                    str(output),
                    "--surface-map",
                    str(surface_map),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            records = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
            ]

        matching = [
            record for record in records if record["source"] == source_text
        ]
        self.assertEqual(len(matching), 2)
        mapped = [record for record in matching if "surface" in record]
        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0]["offset"], raw_start + 8)
        self.assertEqual(mapped[0]["surface"], "cli.help")
        self.assertTrue(mapped[0]["context"]["bun_string_record"])

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
