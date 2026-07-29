from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_initial_corpus import build_corpus


class InitialCorpusBuilderTests(unittest.TestCase):
    def test_builds_sorted_untranslated_units_and_rejects_surrogates(self) -> None:
        records = [
            {
                "source": "Continue with setup",
                "risk": "UNKNOWN",
                "risk_reason": "R-UITEXT",
                "context": {},
            },
            {
                "source": "\ud800",
                "risk": "UNKNOWN",
                "risk_reason": "R-DEFAULT",
                "context": {},
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "records.jsonl"
            source.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            corpus, stats = build_corpus(
                "cli",
                "2.1.112",
                [source],
                "2026-07-29T00:00:00Z",
            )

        self.assertEqual(stats["rejected_invalid_unicode"], 1)
        self.assertEqual(len(corpus["units"]), 1)
        self.assertIsNone(corpus["units"][0]["target"])
        self.assertEqual(corpus["units"][0]["risk"], "UNKNOWN")

    def test_fail_safe_risk_wins_on_normalized_id_collision(self) -> None:
        records = [
            {
                "source": "{count} files changed",
                "risk": "UNKNOWN",
                "risk_reason": "R-UITEXT",
                "context": {},
            },
            {
                "source": "{0} files changed",
                "risk": "FRAGILE",
                "risk_reason": "R-CODEMATCH",
                "context": {},
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "records.jsonl"
            source.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            corpus, stats = build_corpus(
                "cli",
                "2.1.112",
                [source],
                "2026-07-29T00:00:00Z",
            )

        self.assertEqual(stats["normalized_id_collisions"], 1)
        self.assertEqual(corpus["units"][0]["risk"], "FRAGILE")
        self.assertEqual(corpus["units"][0]["source"], "{0} files changed")


if __name__ == "__main__":
    unittest.main()
