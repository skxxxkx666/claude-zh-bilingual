#!/usr/bin/env python3
"""Create review-only LLM suggestions for UNKNOWN R-UITEXT candidates."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from corelib import (  # noqa: E402
    display_width,
    extract_placeholders,
    generate_bilingual,
)
from corelib.pipeline import (  # noqa: E402
    candidate_items,
    extract_pretranslation_template,
    render_pretranslation_prompt,
)


MODELS_URL = "https://models.github.ai/inference/chat/completions"
MODEL = "openai/gpt-4.1"
API_VERSION = "2026-03-10"
BATCH_SIZE = 20


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def _call_github_models(prompt: str, token: str) -> Any:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    request = urllib.request.Request(
        MODELS_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "claude-zh-pipeline/1",
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.load(response)
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("GitHub Models response has no message content") from error
    if not isinstance(content, str):
        raise ValueError("GitHub Models message content must be text")
    if content.lstrip().startswith("```"):
        raise ValueError("GitHub Models returned a forbidden markdown code block")
    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("GitHub Models returned invalid JSON") from error


def validate_suggestions(
    candidates: list[dict[str, Any]],
    raw: Any,
    glossary_terms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reject unknown IDs and fail closed on malformed translation output."""
    if not isinstance(raw, list):
        raise ValueError("pretranslation response must be a JSON array")
    by_id = {item["id"]: item for item in candidates}
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("pretranslation item must be an object")
        identifier = item.get("id")
        if identifier not in by_id:
            raise ValueError(f"pretranslation returned an unknown id: {identifier}")
        if identifier in seen:
            raise ValueError(f"pretranslation returned duplicate id: {identifier}")
        seen.add(identifier)
        source_item = by_id[identifier]
        target = item.get("target")
        confidence = item.get("confidence")
        note = item.get("note", "")
        if target is not None and not isinstance(target, str):
            raise ValueError(f"{identifier}: target must be text or null")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not 0 <= float(confidence) <= 1
        ):
            raise ValueError(f"{identifier}: confidence must be between 0 and 1")
        if not isinstance(note, str):
            raise ValueError(f"{identifier}: note must be text")

        rejection: str | None = None
        if isinstance(target, str):
            if extract_placeholders(target) != source_item["placeholders"]:
                rejection = "pipeline rejected: placeholders do not match"
            elif display_width(target) > source_item["display_width"]:
                rejection = "pipeline rejected: display width exceeds source"
        if rejection:
            target = None
            confidence = 0.0
            note = f"{rejection}; {note}".rstrip("; ")
        validated.append(
            {
                "id": identifier,
                "target": target,
                "target_bilingual": (
                    generate_bilingual(
                        source_item["source"],
                        target,
                        glossary_terms,
                    )
                    if isinstance(target, str)
                    else None
                ),
                "confidence": float(confidence),
                "note": note,
            }
        )
    for identifier in sorted(set(by_id) - seen):
        validated.append(
            {
                "id": identifier,
                "target": None,
                "target_bilingual": None,
                "confidence": 0.0,
                "note": "model omitted this candidate",
            }
        )
    return sorted(validated, key=lambda item: item["id"])


def pretranslate(
    corpus: dict[str, Any],
    glossary: dict[str, Any],
    token: str,
    *,
    limit: int | None = None,
    caller: Callable[[str, str], Any] = _call_github_models,
) -> dict[str, Any]:
    candidates = candidate_items(corpus)
    if limit is not None:
        candidates = candidates[:limit]
    template = extract_pretranslation_template(ROOT / "docs" / "SPEC.md")
    terms = glossary.get("terms", [])
    if not isinstance(terms, list):
        raise ValueError("glossary terms must be an array")
    suggestions: list[dict[str, Any]] = []
    for start in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[start : start + BATCH_SIZE]
        prompt = render_pretranslation_prompt(template, glossary, batch)
        raw = caller(prompt, token)
        suggestions.extend(validate_suggestions(batch, raw, terms))
    low_confidence = [
        item["id"] for item in suggestions if item["confidence"] < 0.8
    ]
    return {
        "target": corpus["target"],
        "version": corpus["version"],
        "model": MODEL,
        "prompt_source": "docs/SPEC.md §8",
        "review_required": True,
        "candidate_count": len(candidates),
        "low_confidence_ids": low_confidence,
        "items": suggestions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("glossary", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("pretranslation failed: GITHUB_TOKEN is required", file=sys.stderr)
        return 1
    try:
        result = pretranslate(
            _load_json(args.corpus),
            _load_json(args.glossary),
            token,
            limit=args.limit,
        )
    except (OSError, ValueError, urllib.error.URLError) as error:
        print(f"pretranslation failed: {error}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as destination:
        json.dump(result, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
    print(
        json.dumps(
            {
                "candidate_count": result["candidate_count"],
                "low_confidence": len(result["low_confidence_ids"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
