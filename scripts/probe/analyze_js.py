#!/usr/bin/env python3
"""Parse the CLI JavaScript bundle and probe risk-classification feasibility."""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


_NODE_DRIVER = r"""
const fs = require("fs");
const acorn = require(process.argv[1]);
const sourcePath = process.argv[2];
const outputPath = process.argv[3];
const metadataPath = process.argv[4];
const source = fs.readFileSync(sourcePath, "utf8");
const started = process.hrtime.bigint();
const ast = acorn.parse(source, {
  ecmaVersion: "latest",
  sourceType: "module",
  allowHashBang: true,
  locations: true,
});
const parsed = process.hrtime.bigint();
const output = fs.openSync(outputPath, "w");
let buffer = [];
let literalCount = 0;

function propertyName(property) {
  if (!property || property.type !== "Property") return null;
  if (!property.computed && property.key.type === "Identifier") {
    return property.key.name;
  }
  if (property.key.type === "Literal" && typeof property.key.value === "string") {
    return property.key.value;
  }
  return null;
}

function memberName(member) {
  if (!member || member.type !== "MemberExpression") return null;
  if (!member.computed && member.property.type === "Identifier") {
    return member.property.name;
  }
  if (member.computed && member.property.type === "Literal") {
    return member.property.value;
  }
  return null;
}

function contextFor(node, parent) {
  const context = {
    property: null,
    comparison: false,
    matcher: null,
    switch_case: false,
  };
  if (!parent) return context;
  if (parent.type === "Property" && parent.value === node) {
    context.property = propertyName(parent);
  }
  if (
    parent.type === "BinaryExpression" &&
    ["===", "!==", "==", "!="].includes(parent.operator)
  ) {
    context.comparison = true;
  }
  if (parent.type === "SwitchCase" && parent.test === node) {
    context.switch_case = true;
  }
  if (parent.type === "CallExpression" && parent.arguments.includes(node)) {
    const method = memberName(parent.callee);
    if (["includes", "startsWith", "match"].includes(method)) {
      context.matcher = method;
    }
  }
  return context;
}

function emit(node, parent, value, kind) {
  const record = {
    value,
    kind,
    start: node.start,
    end: node.end,
    line: node.loc.start.line,
    column: node.loc.start.column,
    parent_type: parent ? parent.type : null,
    context: contextFor(node, parent),
  };
  buffer.push(JSON.stringify(record) + "\n");
  literalCount += 1;
  if (buffer.length >= 5000) {
    fs.writeSync(output, buffer.join(""));
    buffer = [];
  }
}

const stack = [{ node: ast, parent: null }];
while (stack.length) {
  const entry = stack.pop();
  const node = entry.node;
  const parent = entry.parent;
  if (node.type === "Literal" && typeof node.value === "string") {
    emit(node, parent, node.value, "literal");
  } else if (
    node.type === "TemplateLiteral" &&
    node.expressions.length === 0 &&
    node.quasis.length === 1
  ) {
    emit(node, parent, node.quasis[0].value.cooked || "", "template");
  }
  for (const key of Object.keys(node)) {
    if (["start", "end", "loc", "range"].includes(key)) continue;
    const child = node[key];
    if (Array.isArray(child)) {
      for (let index = child.length - 1; index >= 0; index -= 1) {
        const item = child[index];
        if (item && typeof item === "object" && typeof item.type === "string") {
          stack.push({ node: item, parent: node });
        }
      }
    } else if (
      child &&
      typeof child === "object" &&
      typeof child.type === "string"
    ) {
      stack.push({ node: child, parent: node });
    }
  }
}
if (buffer.length) fs.writeSync(output, buffer.join(""));
fs.closeSync(output);
const finished = process.hrtime.bigint();
const memory = process.memoryUsage();
fs.writeFileSync(
  metadataPath,
  JSON.stringify(
    {
      source_bytes: Buffer.byteLength(source, "utf8"),
      literal_count: literalCount,
      parse_seconds: Number(parsed - started) / 1e9,
      total_seconds: Number(finished - started) / 1e9,
      rss_bytes: memory.rss,
      heap_used_bytes: memory.heapUsed,
    },
    null,
    2,
  ) + "\n",
);
"""

_PLACEHOLDER_PATTERNS = (
    re.compile(r"\$\{[^}]*\}"),
    re.compile(r"%\d+\$[sdifx]"),
    re.compile(r"\{[a-zA-Z0-9_]*\}"),
    re.compile(r"%[sdifx]"),
)
_PROMPT_MARKERS = (
    "You are",
    "Your task",
    "IMPORTANT:",
    "<example>",
    "<system",
    "<instructions",
)
_COMMON_UI_WORDS = {
    "cancel",
    "save",
    "retry",
    "continue",
    "loading",
    "done",
    "error",
    "warning",
}


def _has_placeholder(text: str) -> bool:
    return any(pattern.search(text) for pattern in _PLACEHOLDER_PATTERNS)


def _looks_like_identifier(text: str) -> bool:
    stripped = text.strip()
    if not stripped or any(character.isspace() for character in stripped):
        return False
    if stripped.isupper() and any(character.isalpha() for character in stripped):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+", stripped):
        return True
    return (
        "://" in stripped
        or "::" in stripped
        or "/" in stripped
        or "\\" in stripped
        or (
            "." in stripped
            and re.fullmatch(r"[A-Za-z0-9_.@-]+", stripped) is not None
        )
    )


def _looks_like_ui(text: str) -> bool:
    stripped = text.strip()
    if not 4 <= len(stripped) <= 120 or " " not in stripped:
        return False
    first_word = stripped.split(maxsplit=1)[0].casefold()
    return stripped[0].isupper() or first_word in _COMMON_UI_WORDS


def _classify(record: dict[str, Any]) -> tuple[str, str]:
    text = record["value"]
    context = record["context"]
    if context["property"] in {"description", "parameters"}:
        return "DANGER", "R-TOOLDESC"
    if context["comparison"] or context["matcher"] or context["switch_case"]:
        return "FRAGILE", "R-CODEMATCH"
    if len(text) > 200 and text.count(".") >= 2 and not _looks_like_ui(text):
        return "DANGER", "R-LONGPROSE"
    if any(marker in text for marker in _PROMPT_MARKERS):
        return "DANGER", "R-SYSPROMPT"
    if _looks_like_identifier(text):
        return "FRAGILE", "R-IDENTIFIER"
    if _looks_like_ui(text):
        return "UNKNOWN_CANDIDATE", "R-UITEXT"
    return "UNKNOWN", "R-DEFAULT"


def _sample_view(record: dict[str, Any], risk: str, reason: str) -> dict[str, Any]:
    value = record["value"]
    return {
        "line": record["line"],
        "column": record["column"],
        "risk": risk,
        "reason": reason,
        "parent_type": record["parent_type"],
        "context": record["context"],
        "length": len(value),
        "value": value[:240],
        "truncated": len(value) > 240,
    }


def _reservoir_add(
    reservoirs: dict[str, list[dict[str, Any]]],
    seen: Counter[str],
    bucket: str,
    item: dict[str, Any],
    rng: random.Random,
) -> None:
    seen[bucket] += 1
    reservoir = reservoirs[bucket]
    if len(reservoir) < 5:
        reservoir.append(item)
        return
    position = rng.randrange(seen[bucket])
    if position < 5:
        reservoir[position] = item


def analyze(
    node_path: Path,
    acorn_path: Path,
    source_path: Path,
    literals_path: Path,
    parser_metadata_path: Path,
    analysis_path: Path,
) -> None:
    literals_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(node_path),
            "-e",
            _NODE_DRIVER,
            str(acorn_path.resolve()),
            str(source_path.resolve()),
            str(literals_path.resolve()),
            str(parser_metadata_path.resolve()),
        ],
        check=True,
    )

    risk_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    seen: Counter[str] = Counter()
    reservoirs: dict[str, list[dict[str, Any]]] = {
        "DANGER": [],
        "FRAGILE": [],
        "UNKNOWN_CANDIDATE": [],
        "UNKNOWN": [],
    }
    placeholder_count = 0
    rng = random.Random(2112)

    with literals_path.open("r", encoding="utf-8") as records:
        for line in records:
            record = json.loads(line)
            risk, reason = _classify(record)
            risk_counts[risk] += 1
            reason_counts[reason] += 1
            if _has_placeholder(record["value"]):
                placeholder_count += 1
            _reservoir_add(
                reservoirs,
                seen,
                risk,
                _sample_view(record, risk, reason),
                rng,
            )

    total = sum(risk_counts.values())
    parser_metadata = json.loads(
        parser_metadata_path.read_text(encoding="utf-8")
    )
    analysis = {
        "source": str(source_path.resolve()),
        "parser": parser_metadata,
        "total_string_literals": total,
        "risk_counts": dict(risk_counts),
        "risk_percentages": {
            key: round(value * 100 / total, 3)
            for key, value in risk_counts.items()
        },
        "rule_counts": dict(reason_counts),
        "placeholder_literal_count": placeholder_count,
        "review_sample": [
            item
            for bucket in ("DANGER", "FRAGILE", "UNKNOWN_CANDIDATE", "UNKNOWN")
            for item in reservoirs[bucket]
        ],
    }
    analysis_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("acorn", type=Path)
    parser.add_argument("literals", type=Path)
    parser.add_argument("parser_metadata", type=Path)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("--node", type=Path)
    args = parser.parse_args()

    node = args.node or Path(shutil.which("node") or "")
    if not node or not node.exists():
        raise SystemExit("Node.js executable not found")
    analyze(
        node,
        args.acorn,
        args.source,
        args.literals,
        args.parser_metadata,
        args.analysis,
    )


if __name__ == "__main__":
    main()
