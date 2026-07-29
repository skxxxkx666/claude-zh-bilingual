from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from classifiers import classify_file, classify_record


def record(source: str, **context: object) -> dict[str, object]:
    return {"source": source, "context": context}


class ClassifierTests(unittest.TestCase):
    def test_tool_description_is_danger(self) -> None:
        result = classify_record(
            record("Reads a local file.", property="description")
        )
        self.assertEqual((result.risk, result.reason), ("DANGER", "R-TOOLDESC"))

    def test_code_match_is_fragile(self) -> None:
        result = classify_record(record("cancelled", matcher="includes"))
        self.assertEqual((result.risk, result.reason), ("FRAGILE", "R-CODEMATCH"))

    def test_long_prose_is_danger(self) -> None:
        source = "First sentence. Second sentence. " + "x" * 210
        result = classify_record(record(source))
        self.assertEqual((result.risk, result.reason), ("DANGER", "R-LONGPROSE"))

    def test_prompt_marker_is_danger(self) -> None:
        result = classify_record(record("IMPORTANT: follow these instructions"))
        self.assertEqual((result.risk, result.reason), ("DANGER", "R-SYSPROMPT"))

    def test_identifier_is_fragile(self) -> None:
        result = classify_record(record("permission_mode"))
        self.assertEqual((result.risk, result.reason), ("FRAGILE", "R-IDENTIFIER"))

    def test_ui_rule_only_creates_candidate(self) -> None:
        result = classify_record(record("Continue with installation"))
        self.assertEqual(
            (result.risk, result.reason, result.queue),
            ("UNKNOWN", "R-UITEXT", "candidates"),
        )

    def test_locale_context_is_candidate_even_for_one_word(self) -> None:
        result = classify_record(record("Cancel", source_kind="locale"))
        self.assertEqual((result.risk, result.queue), ("UNKNOWN", "candidates"))

    def test_default_is_unknown(self) -> None:
        result = classify_record(record("misc"))
        self.assertEqual(
            (result.risk, result.reason, result.queue),
            ("UNKNOWN", "R-DEFAULT", "unknown"),
        )

    def test_lone_surrogate_is_preserved_as_json_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.jsonl"
            output = root / "queues"
            source.write_text(
                json.dumps({"source": "\ud800", "context": {}}) + "\n",
                encoding="utf-8",
            )
            classify_file(source, output)
            unknown = (output / "unknown.jsonl").read_text(encoding="utf-8")

        self.assertIn("\\ud800", unknown)


if __name__ == "__main__":
    unittest.main()
