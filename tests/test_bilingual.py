from __future__ import annotations

import unittest

from corelib import generate_bilingual


class BilingualGenerationTests(unittest.TestCase):
    def test_does_not_duplicate_an_already_english_product_name(self) -> None:
        terms = [
            {
                "en": "Claude",
                "zh": "Claude",
                "keep_en": True,
                "reason": "PRODUCT_NAME",
            }
        ]

        self.assertEqual(
            generate_bilingual("Open Claude", "打开 Claude", terms),
            "打开 Claude",
        )

    def test_annotates_only_terms_present_in_source_and_target(self) -> None:
        terms = [
            {
                "en": "Cowork",
                "zh": "协作模式",
                "keep_en": True,
                "reason": "PRODUCT_NAME",
            },
            {
                "en": "session",
                "zh": "会话",
                "keep_en": False,
                "reason": "COMMON_TECH",
            },
        ]
        self.assertEqual(
            generate_bilingual(
                "Open a Cowork session",
                "打开协作模式会话",
                terms,
            ),
            "打开协作模式 (Cowork) 会话",
        )

    def test_caps_annotations_at_two_by_reason_priority(self) -> None:
        terms = [
            {
                "en": "Feature",
                "zh": "功能",
                "keep_en": True,
                "reason": "PRODUCT_NAME",
            },
            {
                "en": "Failure",
                "zh": "故障",
                "keep_en": True,
                "reason": "SEARCHABILITY",
            },
            {
                "en": "hook",
                "zh": "钩子",
                "keep_en": True,
                "reason": "DOC_FREQUENCY",
            },
        ]
        self.assertEqual(
            generate_bilingual(
                "Feature Failure hook",
                "功能故障钩子",
                terms,
            ),
            "功能 (Feature) 故障 (Failure) 钩子",
        )

    def test_annotates_each_term_only_once(self) -> None:
        terms = [
            {
                "en": "VM",
                "zh": "虚拟机",
                "keep_en": True,
                "reason": "ECOSYSTEM",
            }
        ]
        self.assertEqual(
            generate_bilingual(
                "Restart VM and remove VM files",
                "重启虚拟机并删除虚拟机文件",
                terms,
            ),
            "重启虚拟机 (VM) 并删除虚拟机文件",
        )


if __name__ == "__main__":
    unittest.main()
