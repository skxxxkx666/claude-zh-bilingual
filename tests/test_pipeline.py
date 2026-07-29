from __future__ import annotations

import unittest
from pathlib import Path

from corelib.pipeline import (
    candidate_items,
    extract_pretranslation_template,
    inherit_corpus,
    render_pr_body,
)
from corelib.text import display_width, extract_placeholders, unit_id


ROOT = Path(__file__).resolve().parents[1]


def unit(
    source: str,
    *,
    risk: str = "SAFE",
    surface: str = "cli.ast.literal",
    target: str | None = "继续",
) -> dict[str, object]:
    return {
        "id": unit_id(source),
        "source": source,
        "target": target,
        "target_bilingual": target,
        "risk": risk,
        "risk_reason": "manual review",
        "surface": surface,
        "byte_budget": len(source.encode("utf-8")),
        "display_width": display_width(source),
        "placeholders": extract_placeholders(source),
        "seen_in": ["cli@2.1.111"],
        "verified_at": "cli@2.1.111" if target else None,
        "deprecated": False,
        "notes": "",
    }


def corpus(*units: dict[str, object]) -> dict[str, object]:
    return {
        "format_version": "1.0.0",
        "target": "cli",
        "version": "2.1.111",
        "generated_at": "2026-07-29T00:00:00Z",
        "units": list(units),
    }


def record(
    source: str,
    *,
    surface: str = "cli.ast.literal",
    **context: object,
) -> dict[str, object]:
    return {
        "source": source,
        "extractor": "js-ast",
        "surface": surface,
        "context": context,
    }


class PipelineTests(unittest.TestCase):
    def test_inherits_stable_safe_translation(self) -> None:
        old = corpus(unit("Continue with setup"))
        updated, report = inherit_corpus(
            old,
            [record("Continue with setup")],
            "cli",
            "2.1.112",
            "2026-07-30T00:00:00Z",
        )

        current = updated["units"][0]
        self.assertEqual(report["inherited"], 1)
        self.assertEqual(current["target"], "继续")
        self.assertEqual(current["verified_at"], "cli@2.1.112")
        self.assertEqual(
            current["seen_in"],
            ["cli@2.1.111", "cli@2.1.112"],
        )

    def test_surface_change_cannot_inherit_safe(self) -> None:
        old = corpus(unit("Continue with setup", surface="cli.tui.status"))
        updated, report = inherit_corpus(
            old,
            [record("Continue with setup", surface="cli.tool.description")],
            "cli",
            "2.1.112",
            "2026-07-30T00:00:00Z",
        )

        current = updated["units"][0]
        self.assertEqual(report["surface_changes"], 1)
        self.assertEqual(current["risk"], "UNKNOWN")
        self.assertIsNone(current["target"])
        self.assertEqual(report["alerts"][0]["reason"], "SURFACE-CHANGED")

    def test_safe_to_danger_recheck_clears_translation(self) -> None:
        old = corpus(unit("Continue with setup"))
        updated, report = inherit_corpus(
            old,
            [record("Continue with setup", property="description")],
            "cli",
            "2.1.112",
            "2026-07-30T00:00:00Z",
        )

        current = updated["units"][0]
        self.assertEqual(current["risk"], "DANGER")
        self.assertEqual(current["risk_reason"], "R-TOOLDESC")
        self.assertIsNone(current["target"])
        self.assertIsNone(current["target_bilingual"])
        self.assertIsNone(current["verified_at"])
        self.assertEqual(report["downgrade_alerts"], 1)

    def test_source_placeholder_change_cannot_inherit(self) -> None:
        old = corpus(
            unit("{count} files changed"),
            unit("Continue with setup"),
        )
        updated, report = inherit_corpus(
            old,
            [
                record("{0} files changed"),
                record("Continue with setup"),
            ],
            "cli",
            "2.1.112",
            "2026-07-30T00:00:00Z",
        )

        current = next(
            item
            for item in updated["units"]
            if item["source"] == "{0} files changed"
        )
        self.assertEqual(report["source_changes"], 1)
        self.assertEqual(report["reclassified"], 1)
        self.assertEqual(report["inheritance_rate"], 0.5)
        self.assertEqual(report["retention_rate"], 1.0)
        self.assertEqual(current["source"], "{0} files changed")
        self.assertEqual(current["placeholders"], ["{0}"])
        self.assertIsNone(current["target"])

    def test_only_new_candidates_enter_corpus(self) -> None:
        updated, report = inherit_corpus(
            corpus(),
            [
                record("Continue with setup"),
                record("Reads a local file.", property="description"),
                record("permission_mode"),
                record("misc"),
            ],
            "cli",
            "2.1.112",
            "2026-07-30T00:00:00Z",
        )

        self.assertEqual(report["new"], 1)
        self.assertEqual(report["omitted_new_non_candidates"], 3)
        self.assertEqual(
            [item["source"] for item in updated["units"]],
            ["Continue with setup"],
        )

    def test_missing_unit_is_deprecated_not_deleted(self) -> None:
        old = corpus(unit("Continue with setup"))
        updated, report = inherit_corpus(
            old,
            [],
            "cli",
            "2.1.112",
            "2026-07-30T00:00:00Z",
        )

        self.assertEqual(report["disappeared"], 1)
        self.assertTrue(updated["units"][0]["deprecated"])

    def test_prompt_is_read_verbatim_and_candidates_are_fail_safe(self) -> None:
        template = extract_pretranslation_template(ROOT / "docs" / "SPEC.md")
        self.assertTrue(template.startswith("你是 claude-zh-bilingual 项目的翻译器。"))
        self.assertIn("{{GLOSSARY_JSON}}", template)
        self.assertIn("{{ITEMS_JSON}}", template)

        candidate = unit("Continue with setup", risk="UNKNOWN", target=None)
        candidate["risk_reason"] = "R-UITEXT"
        danger = unit("Reads a file.", risk="DANGER", target=None)
        danger["risk_reason"] = "R-TOOLDESC"
        self.assertEqual(
            [item["id"] for item in candidate_items(corpus(candidate, danger))],
            [candidate["id"]],
        )

    def test_pr_body_contains_required_summary_and_lists(self) -> None:
        body = render_pr_body(
            {
                "new": 3,
                "inherited": 10,
                "downgrade_alerts": 1,
                "disappeared": 2,
                "inheritance_rate": 10 / 13,
                "alerts": [
                    {
                        "id": "0123456789abcdef",
                        "from": "SAFE",
                        "to": "DANGER",
                        "reason": "R-TOOLDESC",
                    }
                ],
            },
            [
                {
                    "id": "fedcba9876543210",
                    "confidence": 0.75,
                    "note": "context",
                }
            ],
        )

        self.assertIn("新增 3 条 / 继承 10 条 / 降级告警 1 条 / 消失 2 条", body)
        self.assertIn("0123456789abcdef", body)
        self.assertIn("fedcba9876543210", body)
        self.assertIn("禁止自动合并", body)


if __name__ == "__main__":
    unittest.main()
