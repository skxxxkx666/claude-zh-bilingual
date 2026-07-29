from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.release_status import LAST_JS_CLI_VERSION, corpus_lifecycle


class ReleaseStatusTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
