from __future__ import annotations

import unittest

from corelib.text import display_width, extract_placeholders, unit_id
from scripts.pretranslate import pretranslate, validate_suggestions


def candidate(source: str) -> dict[str, object]:
    return {
        "id": unit_id(source),
        "source": source,
        "target": None,
        "target_bilingual": None,
        "risk": "UNKNOWN",
        "risk_reason": "R-UITEXT",
        "surface": "cli.ast.literal",
        "byte_budget": len(source.encode("utf-8")),
        "display_width": display_width(source),
        "placeholders": extract_placeholders(source),
        "seen_in": ["cli@2.1.112"],
        "verified_at": None,
        "deprecated": False,
        "notes": "",
    }


class PretranslationTests(unittest.TestCase):
    def test_only_candidates_are_sent_with_exact_spec_prompt(self) -> None:
        current = candidate("Cancel operation")
        danger = candidate("Reads a local file")
        danger["risk"] = "DANGER"
        danger["risk_reason"] = "R-TOOLDESC"
        prompts: list[str] = []

        def caller(prompt: str, token: str) -> object:
            prompts.append(prompt)
            self.assertEqual(token, "test-token")
            return [
                {
                    "id": current["id"],
                    "target": "取消操作",
                    "confidence": 0.9,
                    "note": "",
                }
            ]

        result = pretranslate(
            {
                "target": "cli",
                "version": "2.1.112",
                "units": [current, danger],
            },
            {"version": "0.1.0", "terms": []},
            "test-token",
            caller=caller,
        )

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(len(prompts), 1)
        self.assertTrue(
            prompts[0].startswith(
                "你是 claude-zh-bilingual 项目的翻译器。"
            )
        )
        self.assertNotIn("Reads a local file", prompts[0])
        self.assertEqual(result["items"][0]["target"], "取消操作")

    def test_width_violation_is_rejected_for_human_review(self) -> None:
        source = candidate("Cancel")
        result = validate_suggestions(
            [source],
            [
                {
                    "id": source["id"],
                    "target": "这是一个非常非常长的取消操作",
                    "confidence": 0.95,
                    "note": "",
                }
            ],
            [],
        )

        self.assertIsNone(result[0]["target"])
        self.assertEqual(result[0]["confidence"], 0.0)
        self.assertIn("display width", result[0]["note"])

    def test_placeholder_violation_is_rejected(self) -> None:
        source = candidate("Changed {count} files")
        result = validate_suggestions(
            [source],
            [
                {
                    "id": source["id"],
                    "target": "已更改文件",
                    "confidence": 0.9,
                    "note": "",
                }
            ],
            [],
        )

        self.assertIsNone(result[0]["target"])
        self.assertIn("placeholders", result[0]["note"])

    def test_unknown_model_id_fails_closed(self) -> None:
        source = candidate("Cancel operation")
        with self.assertRaisesRegex(ValueError, "unknown id"):
            validate_suggestions(
                [source],
                [
                    {
                        "id": "0000000000000000",
                        "target": "取消操作",
                        "confidence": 0.9,
                        "note": "",
                    }
                ],
                [],
            )


if __name__ == "__main__":
    unittest.main()
