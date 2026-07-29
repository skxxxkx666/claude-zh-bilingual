"""Fail-safe corpus inheritance and W7-8 automation helpers."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from classifiers import Classification, classify_record

from .text import display_width, extract_placeholders, unit_id


_CLASSIFICATION_PRIORITY = {
    ("DANGER", "excluded"): 4,
    ("FRAGILE", "excluded"): 3,
    ("UNKNOWN", "candidates"): 2,
    ("UNKNOWN", "unknown"): 1,
}


def _version_key(value: str) -> tuple[str, tuple[int, int, int]]:
    target, version = value.split("@", maxsplit=1)
    return target, tuple(int(part) for part in version.split("."))


def _surface(record: dict[str, Any], target: str) -> str:
    explicit = record.get("surface")
    if isinstance(explicit, str) and explicit.startswith(f"{target}."):
        return explicit
    context = record.get("context") or {}
    if context.get("source_kind") == "locale":
        return "desktop.locale.catalog"
    if record.get("extractor") == "binary":
        return f"{target}.binary.literal"
    return f"{target}.ast.literal"


def _valid_source(value: object) -> bool:
    if not isinstance(value, str) or not value or len(value) > 500:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


@dataclass
class _SourceSummary:
    source: str
    classification: Classification
    representative: dict[str, Any]
    surfaces: set[str] = field(default_factory=set)

    def add(
        self,
        record: dict[str, Any],
        classification: Classification,
        surface: str,
    ) -> None:
        self.surfaces.add(surface)
        current_rank = _CLASSIFICATION_PRIORITY[
            (self.classification.risk, self.classification.queue)
        ]
        candidate_rank = _CLASSIFICATION_PRIORITY[
            (classification.risk, classification.queue)
        ]
        if candidate_rank > current_rank:
            self.classification = classification
            self.representative = record


@dataclass
class _UnitSummary:
    identifier: str
    sources: dict[str, _SourceSummary] = field(default_factory=dict)
    classification: Classification | None = None
    representative: dict[str, Any] | None = None

    def add(self, record: dict[str, Any], target: str) -> None:
        source = record["source"]
        classification = classify_record(record)
        surface = _surface(record, target)
        if source not in self.sources:
            self.sources[source] = _SourceSummary(
                source=source,
                classification=classification,
                representative=record,
                surfaces={surface},
            )
        else:
            self.sources[source].add(record, classification, surface)

        if self.classification is None:
            self.classification = classification
            self.representative = record
            return
        current_rank = _CLASSIFICATION_PRIORITY[
            (self.classification.risk, self.classification.queue)
        ]
        candidate_rank = _CLASSIFICATION_PRIORITY[
            (classification.risk, classification.queue)
        ]
        if candidate_rank > current_rank:
            self.classification = classification
            self.representative = record
        elif candidate_rank == current_rank:
            current_source = str(self.representative["source"])
            candidate_source = str(record["source"])
            if (len(candidate_source.encode("utf-8")), candidate_source) < (
                len(current_source.encode("utf-8")),
                current_source,
            ):
                self.representative = record


def summarize_records(
    records: Iterable[dict[str, Any]],
    target: str,
) -> tuple[dict[str, _UnitSummary], dict[str, int]]:
    """Group extractor records without persisting excluded upstream prose."""
    grouped: dict[str, _UnitSummary] = {}
    stats = {"input_records": 0, "invalid_records": 0}
    for record in records:
        stats["input_records"] += 1
        source = record.get("source")
        if not _valid_source(source):
            stats["invalid_records"] += 1
            continue
        identifier = unit_id(source)
        grouped.setdefault(identifier, _UnitSummary(identifier)).add(record, target)
    return grouped, stats


def read_jsonl(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        with path.open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"{path}:{line_number}: {error}") from error
                if not isinstance(record, dict):
                    raise ValueError(f"{path}:{line_number}: record must be an object")
                yield record


def _new_unit(
    summary: _UnitSummary,
    target: str,
    version_marker: str,
) -> dict[str, Any]:
    assert summary.classification is not None
    assert summary.representative is not None
    record = summary.representative
    source = record["source"]
    return {
        "id": summary.identifier,
        "source": source,
        "target": None,
        "target_bilingual": None,
        "risk": "UNKNOWN",
        "risk_reason": summary.classification.reason,
        "surface": _surface(record, target),
        "byte_budget": len(source.encode("utf-8")),
        "display_width": display_width(source),
        "placeholders": extract_placeholders(source),
        "seen_in": [version_marker],
        "verified_at": None,
        "deprecated": False,
        "notes": "",
    }


def _clear_translation(unit: dict[str, Any]) -> None:
    unit["target"] = None
    unit["target_bilingual"] = None
    unit["verified_at"] = None


def _reset_unit(
    unit: dict[str, Any],
    source_summary: _SourceSummary,
    target: str,
) -> None:
    source = source_summary.source
    classification = source_summary.classification
    unit["source"] = source
    unit["risk"] = classification.risk
    unit["risk_reason"] = classification.reason
    unit["surface"] = min(source_summary.surfaces) or _surface(
        source_summary.representative,
        target,
    )
    unit["byte_budget"] = len(source.encode("utf-8"))
    unit["display_width"] = display_width(source)
    unit["placeholders"] = extract_placeholders(source)
    _clear_translation(unit)


def inherit_corpus(
    old_corpus: dict[str, Any],
    records: Iterable[dict[str, Any]],
    target: str,
    new_version: str,
    generated_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply SPEC section 4 inheritance with surface and SAFE rechecks."""
    grouped, input_stats = summarize_records(records, target)
    old_units = {
        unit["id"]: copy.deepcopy(unit)
        for unit in old_corpus.get("units", [])
        if isinstance(unit, dict) and isinstance(unit.get("id"), str)
    }
    version_marker = f"{target}@{new_version}"
    output: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    new_ids: list[str] = []
    disappeared_ids: list[str] = []
    counts = {
        **input_stats,
        "new": 0,
        "inherited": 0,
        "downgrade_alerts": 0,
        "disappeared": 0,
        "surface_changes": 0,
        "source_changes": 0,
        "reclassified": 0,
        "omitted_new_non_candidates": 0,
    }

    for identifier, summary in grouped.items():
        classification = summary.classification
        assert classification is not None
        if identifier not in old_units:
            if (
                classification.risk == "UNKNOWN"
                and classification.queue == "candidates"
            ):
                output.append(_new_unit(summary, target, version_marker))
                counts["new"] += 1
                new_ids.append(identifier)
            else:
                counts["omitted_new_non_candidates"] += 1
            continue

        unit = old_units.pop(identifier)
        old_risk = unit["risk"]
        old_source = unit["source"]
        source_summary = summary.sources.get(old_source)
        source_changed = source_summary is None
        if source_summary is None:
            representative_source = str(summary.representative["source"])
            source_summary = summary.sources[representative_source]
            counts["source_changes"] += 1

        old_surface = unit["surface"]
        surface_changed = old_surface not in source_summary.surfaces
        if surface_changed:
            counts["surface_changes"] += 1

        dangerous_recheck = (
            old_risk == "SAFE"
            and classification.risk in {"DANGER", "FRAGILE"}
        )
        if dangerous_recheck:
            counts["reclassified"] += 1
            _reset_unit(unit, source_summary, target)
            unit["risk"] = classification.risk
            unit["risk_reason"] = classification.reason
            alerts.append(
                {
                    "id": identifier,
                    "from": old_risk,
                    "to": classification.risk,
                    "reason": classification.reason,
                    "surface_from": old_surface,
                    "surface_to": unit["surface"],
                }
            )
        elif source_changed or surface_changed:
            counts["reclassified"] += 1
            _reset_unit(unit, source_summary, target)
            if old_risk == "SAFE":
                alerts.append(
                    {
                        "id": identifier,
                        "from": old_risk,
                        "to": unit["risk"],
                        "reason": (
                            "SOURCE-CHANGED" if source_changed else "SURFACE-CHANGED"
                        ),
                        "surface_from": old_surface,
                        "surface_to": unit["surface"],
                    }
                )
        else:
            counts["inherited"] += 1
            source = unit["source"]
            unit["byte_budget"] = len(source.encode("utf-8"))
            unit["display_width"] = display_width(source)
            unit["placeholders"] = extract_placeholders(source)
            if unit["risk"] == "SAFE" and unit.get("target"):
                unit["verified_at"] = version_marker

        seen_in = set(unit.get("seen_in", []))
        seen_in.add(version_marker)
        unit["seen_in"] = sorted(seen_in, key=_version_key)
        unit["deprecated"] = False
        output.append(unit)

    for identifier, unit in old_units.items():
        unit["deprecated"] = True
        output.append(unit)
        counts["disappeared"] += 1
        disappeared_ids.append(identifier)

    output.sort(key=lambda unit: unit["id"])
    counts["downgrade_alerts"] = len(alerts)
    current_denominator = (
        counts["inherited"] + counts["reclassified"] + counts["new"]
    )
    previous_denominator = (
        counts["inherited"] + counts["reclassified"] + counts["disappeared"]
    )
    report: dict[str, Any] = {
        **counts,
        "target": target,
        "version": new_version,
        "inheritance_rate": (
            counts["inherited"] / current_denominator
            if current_denominator
            else 1.0
        ),
        "retention_rate": (
            (counts["inherited"] + counts["reclassified"]) / previous_denominator
            if previous_denominator
            else 1.0
        ),
        "alerts": sorted(alerts, key=lambda alert: alert["id"]),
        "new_ids": sorted(new_ids)[:200],
        "new_ids_truncated": max(0, len(new_ids) - 200),
        "disappeared_ids": sorted(disappeared_ids)[:200],
        "disappeared_ids_truncated": max(0, len(disappeared_ids) - 200),
    }
    corpus = {
        "format_version": old_corpus.get("format_version", "1.0.0"),
        "target": target,
        "version": new_version,
        "generated_at": generated_at,
        "units": output,
    }
    return corpus, report


def extract_pretranslation_template(spec_path: Path) -> str:
    """Read the fenced SPEC section 8 prompt instead of duplicating it."""
    text = spec_path.read_text(encoding="utf-8")
    heading = "## 8. LLM 预翻译 Prompt(流水线用)"
    start = text.index(heading)
    fence_start = text.index("```", start) + 3
    if text[fence_start : fence_start + 2] == "\r\n":
        fence_start += 2
    elif text[fence_start : fence_start + 1] == "\n":
        fence_start += 1
    fence_end = text.index("```", fence_start)
    return text[fence_start:fence_end].rstrip("\r\n")


def candidate_items(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only untranslated R-UITEXT candidates for LLM review."""
    return [
        {
            "id": unit["id"],
            "source": unit["source"],
            "surface": unit["surface"],
            "byte_budget": unit["byte_budget"],
            "display_width": unit["display_width"],
            "placeholders": unit["placeholders"],
        }
        for unit in corpus.get("units", [])
        if unit.get("risk") == "UNKNOWN"
        and unit.get("risk_reason") == "R-UITEXT"
        and not unit.get("deprecated", False)
        and not unit.get("target")
    ]


def render_pretranslation_prompt(
    template: str,
    glossary: dict[str, Any],
    items: list[dict[str, Any]],
) -> str:
    glossary_json = json.dumps(
        glossary,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    items_json = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
    return template.replace("{{GLOSSARY_JSON}}", glossary_json).replace(
        "{{ITEMS_JSON}}",
        items_json,
    )


def render_pr_body(
    report: dict[str, Any],
    low_confidence: Iterable[dict[str, Any]] = (),
) -> str:
    low_confidence = list(low_confidence)
    lines = [
        "## 自动版本适配",
        "",
        (
            f"新增 {report['new']} 条 / 继承 {report['inherited']} 条 / "
            f"降级告警 {report['downgrade_alerts']} 条 / "
            f"消失 {report['disappeared']} 条"
        ),
        "",
        f"继承率：{report['inheritance_rate']:.2%}",
        "",
        "### 风险降级告警",
        "",
    ]
    alerts = report.get("alerts", [])
    if alerts:
        for alert in alerts:
            lines.append(
                f"- `{alert['id']}`: {alert['from']} → {alert['to']} "
                f"({alert['reason']})"
            )
    else:
        lines.append("- 无")
    lines.extend(["", "### 低置信度译文（confidence < 0.8）", ""])
    if low_confidence:
        for item in low_confidence:
            lines.append(
                f"- `{item['id']}`: {item['confidence']:.2f} — "
                f"{item.get('note') or '未说明'}"
            )
    else:
        lines.append("- 无")
    lines.extend(["", "> 此 PR 仅自动生成，禁止自动合并。", ""])
    return "\n".join(lines)
