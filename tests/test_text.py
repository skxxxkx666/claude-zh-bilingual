from __future__ import annotations

import json
import unittest
from pathlib import Path

from corelib import display_width, extract_placeholders, normalize, unit_id


class UnitIdTests(unittest.TestCase):
    def test_spec_vectors(self) -> None:
        vectors = {
            "Continue?": "5c21be5ac90305e2",
            "  Continue?  ": "5c21be5ac90305e2",
            "{0} files changed": "91e30b891f6098b1",
            "{count} files changed": "91e30b891f6098b1",
            "%s files changed": "91e30b891f6098b1",
            "\x1b[32mDone\x1b[0m": "11a6767d5674c7e4",
            "Done": "11a6767d5674c7e4",
        }
        for source, expected in vectors.items():
            with self.subTest(source=source):
                self.assertEqual(unit_id(source), expected)

    def test_internal_whitespace_is_not_collapsed(self) -> None:
        self.assertNotEqual(unit_id("A  B"), unit_id("A B"))

    def test_unicode_is_normalized_to_nfc(self) -> None:
        self.assertEqual(normalize("Cafe\u0301"), normalize("Caf\u00e9"))


class PlaceholderTests(unittest.TestCase):
    def test_preserves_order_and_repeats_without_overlap(self) -> None:
        source = "${name} {0} %1$s %s {0}"
        self.assertEqual(
            extract_placeholders(source),
            ["${name}", "{0}", "%1$s", "%s", "{0}"],
        )

    def test_placeholder_spellings_share_an_id(self) -> None:
        self.assertEqual(
            unit_id("{count} files changed"),
            unit_id("%s files changed"),
        )


class DisplayWidthTests(unittest.TestCase):
    def test_ascii_and_cjk(self) -> None:
        self.assertEqual(display_width("A中"), 3)

    def test_combining_and_control_characters(self) -> None:
        self.assertEqual(display_width("e\u0301"), 1)
        self.assertEqual(display_width("\x00"), 0)


class SchemaExampleTests(unittest.TestCase):
    def test_unit_schema_examples_match_core_algorithms(self) -> None:
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "schema"
            / "unit.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        for example in schema["examples"]:
            source = example["source"]
            with self.subTest(source=source):
                self.assertEqual(example["id"], unit_id(source))
                self.assertEqual(
                    example["byte_budget"],
                    len(source.encode("utf-8")),
                )
                self.assertEqual(
                    example["display_width"],
                    display_width(source),
                )
                self.assertEqual(
                    example["placeholders"],
                    extract_placeholders(source),
                )


if __name__ == "__main__":
    unittest.main()
