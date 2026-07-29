import json
import tempfile
import unittest
from pathlib import Path

from scripts.apply_desktop_review import apply_review


class DesktopReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.corpus_path = self.root / "corpus.json"
        self.glossary_path = self.root / "glossary.json"
        self.review_path = self.root / "review.json"
        self.unit = {
            "id": "0123456789abcdef",
            "source": "Open Claude Settings",
            "target": None,
            "target_bilingual": None,
            "risk": "UNKNOWN",
            "risk_reason": "R-UITEXT",
            "surface": "desktop.locale.catalog",
            "verified_at": None,
            "notes": "",
        }
        self._write(
            self.corpus_path,
            {"target": "desktop", "units": [self.unit]},
        )
        self._write(
            self.glossary_path,
            {
                "terms": [
                    {
                        "en": "Claude",
                        "zh": "Claude",
                        "keep_en": True,
                        "reason": "PRODUCT_NAME",
                    }
                ]
            },
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def _write(path: Path, value: object) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_applies_only_reviewed_locale_catalog_unit(self) -> None:
        self._write(
            self.review_path,
            [
                {
                    "id": self.unit["id"],
                    "target": "打开 Claude 设置",
                }
            ],
        )

        corpus, count = apply_review(
            self.corpus_path,
            self.glossary_path,
            self.review_path,
        )

        updated = corpus["units"][0]
        self.assertEqual(count, 1)
        self.assertEqual(updated["risk"], "SAFE")
        self.assertEqual(updated["target"], "打开 Claude 设置")
        self.assertEqual(updated["target_bilingual"], "打开 Claude 设置")
        self.assertIsNone(updated["verified_at"])

    def test_rejects_source_mismatch(self) -> None:
        self._write(
            self.review_path,
            [
                {
                    "id": self.unit["id"],
                    "source": "Changed source",
                    "target": "打开设置",
                }
            ],
        )

        with self.assertRaisesRegex(ValueError, "source mismatch"):
            apply_review(
                self.corpus_path,
                self.glossary_path,
                self.review_path,
            )

    def test_allows_idempotent_w3_review_update(self) -> None:
        self.unit["risk"] = "SAFE"
        self.unit["target"] = "旧译文"
        self.unit["notes"] = "W3 manual review; pending D1-D4 verification"
        self._write(
            self.corpus_path,
            {"target": "desktop", "units": [self.unit]},
        )
        self._write(
            self.review_path,
            [{"id": self.unit["id"], "target": "打开 Claude 设置"}],
        )

        corpus, count = apply_review(
            self.corpus_path,
            self.glossary_path,
            self.review_path,
        )

        self.assertEqual(count, 1)
        self.assertEqual(corpus["units"][0]["target"], "打开 Claude 设置")

    def test_review_file_is_source_of_truth_for_w3_units(self) -> None:
        self.unit["risk"] = "SAFE"
        self.unit["target"] = "旧译文"
        self.unit["target_bilingual"] = "旧译文"
        self.unit["notes"] = "W3 manual review; pending D1-D4 verification"
        self._write(
            self.corpus_path,
            {"target": "desktop", "units": [self.unit]},
        )
        self._write(self.review_path, [])

        corpus, count = apply_review(
            self.corpus_path,
            self.glossary_path,
            self.review_path,
        )

        updated = corpus["units"][0]
        self.assertEqual(count, 0)
        self.assertEqual(updated["risk"], "UNKNOWN")
        self.assertIsNone(updated["target"])
        self.assertEqual(updated["notes"], "")

    def test_marks_reviewed_units_after_complete_smoke_verification(self) -> None:
        self._write(
            self.review_path,
            [{"id": self.unit["id"], "target": "打开 Claude 设置"}],
        )

        corpus, count = apply_review(
            self.corpus_path,
            self.glossary_path,
            self.review_path,
            "desktop@1.18286.0",
        )

        updated = corpus["units"][0]
        self.assertEqual(count, 1)
        self.assertEqual(updated["verified_at"], "desktop@1.18286.0")
        self.assertEqual(updated["notes"], "W3 manual review; D1-D4 verified")


if __name__ == "__main__":
    unittest.main()
