#!/usr/bin/env python3
"""Extract JavaScript string literals with compact AST context."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
_NODE_DRIVER = r"""
const fs = require("fs");
const acorn = require(process.argv[1]);
const sourcePath = process.argv[2];
const outputPath = process.argv[3];
const target = process.argv[4];
const version = process.argv[5];
const append = process.argv[6] === "append";
const source = fs.readFileSync(sourcePath, "utf8");
const ast = acorn.parse(source, {
  ecmaVersion: "latest",
  sourceType: "module",
  allowHashBang: true,
  locations: true,
});
const output = fs.openSync(outputPath, append ? "a" : "w");
let buffer = [];
let count = 0;

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

function contextFor(node, parent, kind) {
  const context = {
    kind,
    parent_type: parent ? parent.type : null,
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
  if (!value) return;
  const record = {
    source: value,
    target,
    version,
    extractor: "js-ast",
    container: sourcePath,
    offset: node.start,
    offset_unit: "utf16_code_unit",
    byte_length: Buffer.byteLength(value, "utf8"),
    encoding: "utf-8",
    line: node.loc.start.line,
    column: node.loc.start.column,
    context: contextFor(node, parent, kind),
  };
  buffer.push(JSON.stringify(record) + "\n");
  count += 1;
  if (buffer.length >= 5000) {
    fs.writeSync(output, buffer.join(""));
    buffer = [];
  }
}

const stack = [{ node: ast, parent: null }];
while (stack.length) {
  const { node, parent } = stack.pop();
  if (node.type === "Literal" && typeof node.value === "string") {
    emit(node, parent, node.value, "literal");
  } else if (node.type === "TemplateLiteral") {
    let value = "";
    for (let index = 0; index < node.quasis.length; index += 1) {
      value += node.quasis[index].value.cooked || "";
      if (index < node.expressions.length) {
        const expression = node.expressions[index];
        value += "${" + source.slice(expression.start, expression.end) + "}";
      }
    }
    emit(node, parent, value, "template");
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
process.stdout.write(JSON.stringify({ extracted: count }) + "\n");
"""


def extract(
    source: Path,
    output: Path,
    target: str,
    version: str,
    node: Path,
    acorn: Path,
    append: bool = False,
) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            str(node),
            "-e",
            _NODE_DRIVER,
            str(acorn.resolve()),
            str(source.resolve()),
            str(output.resolve()),
            target,
            version,
            "append" if append else "truncate",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return int(json.loads(result.stdout)["extracted"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", choices=("cli", "desktop"))
    parser.add_argument("version")
    parser.add_argument("output", type=Path)
    parser.add_argument("--node", type=Path)
    parser.add_argument(
        "--acorn",
        type=Path,
        default=ROOT / "node_modules" / "acorn" / "dist" / "acorn.js",
    )
    args = parser.parse_args()

    node = args.node or Path(shutil.which("node") or "")
    if not node.is_file():
        raise SystemExit("Node.js executable not found")
    if not args.acorn.is_file():
        raise SystemExit(f"Acorn parser not found: {args.acorn}")
    sources = (
        sorted(args.source.rglob("*.js"))
        if args.source.is_dir()
        else [args.source]
    )
    if not sources:
        raise SystemExit(f"no JavaScript files found under {args.source}")
    count = 0
    for index, source in enumerate(sources):
        try:
            count += extract(
                source,
                args.output,
                args.target,
                args.version,
                node,
                args.acorn,
                append=index > 0,
            )
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or "").strip()
            raise SystemExit(f"failed to parse {source}: {detail}") from error
    print(json.dumps({"files": len(sources), "extracted": count}))


if __name__ == "__main__":
    main()
