"""Build the retrieval corpus from the target application.

`knowledge/chunks.jsonl` is generated, never hand-edited, so it cannot drift from
the code it describes. Ordering is deterministic: the same tree always produces a
byte-identical file.

Fix notes are harvested from dev fixtures only, and carry a defect's category,
module and one-line summary. They never carry a reference patch, a failing test
or a fixture's notes.md — those are scoring material, not prompt material.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_APP = PROJECT_ROOT / "target_app"
KNOWLEDGE = PROJECT_ROOT / "knowledge"
FIXTURES = PROJECT_ROOT / "fixtures"
OUTPUT = KNOWLEDGE / "chunks.jsonl"

MIN_FUNCTION_LINES = 10
KIND_ORDER = {"module": 0, "function": 1, "test": 2, "convention": 3, "fix_note": 4}

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def signature_of(node: FunctionNode) -> str:
    """The def line, without the body."""
    parts = [f"def {node.name}("]
    arguments = node.args
    rendered: list[str] = []
    positional = list(arguments.posonlyargs) + list(arguments.args)
    defaults = list(arguments.defaults)
    padding = len(positional) - len(defaults)
    for index, argument in enumerate(positional):
        text = argument.arg
        if argument.annotation is not None:
            text += f": {ast.unparse(argument.annotation)}"
        if index >= padding:
            text += f" = {ast.unparse(defaults[index - padding])}"
        rendered.append(text)
    if arguments.vararg is not None:
        rendered.append(f"*{arguments.vararg.arg}")
    for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True):
        text = argument.arg
        if argument.annotation is not None:
            text += f": {ast.unparse(argument.annotation)}"
        if default is not None:
            text += f" = {ast.unparse(default)}"
        rendered.append(text)
    if arguments.kwarg is not None:
        rendered.append(f"**{arguments.kwarg.arg}")
    parts.append(", ".join(rendered))
    parts.append(")")
    if node.returns is not None:
        parts.append(f" -> {ast.unparse(node.returns)}")
    return "".join(parts) + ":"


def source_span(source_lines: list[str], node: ast.AST) -> str:
    start = node.lineno - 1
    for decorator in getattr(node, "decorator_list", []):
        start = min(start, decorator.lineno - 1)
    end = node.end_lineno or node.lineno
    return "".join(source_lines[start:end]).rstrip("\n")


def top_level_functions(tree: ast.Module) -> list[FunctionNode]:
    found: list[FunctionNode] = []
    for node in tree.body:
        if isinstance(node, FunctionNode):
            found.append(node)
        elif isinstance(node, ast.ClassDef):
            found.extend(child for child in node.body if isinstance(child, FunctionNode))
    return found


def module_chunk(path: Path, relative: str, tree: ast.Module) -> dict:
    docstring = ast.get_docstring(tree) or ""
    signatures = [
        signature_of(node) for node in top_level_functions(tree) if not node.name.startswith("_")
    ]
    classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    body = [f"Module `{relative}`", ""]
    if docstring:
        body.extend([docstring, ""])
    if classes:
        body.append("Classes: " + ", ".join(sorted(set(classes))))
        body.append("")
    body.append("Public signatures:")
    body.extend(f"    {signature}" for signature in signatures)
    return {
        "chunk_id": f"module:{relative}",
        "source_path": relative,
        "kind": "module",
        "text": "\n".join(body).rstrip() + "\n",
        "score": 0.0,
    }


def function_chunks(relative: str, tree: ast.Module, source_lines: list[str]) -> list[dict]:
    chunks: list[dict] = []
    for node in top_level_functions(tree):
        span = (node.end_lineno or node.lineno) - node.lineno + 1
        if span < MIN_FUNCTION_LINES:
            continue
        docstring = ast.get_docstring(node) or ""
        header = f"`{relative}` — {signature_of(node)}"
        parts = [header, ""]
        if docstring:
            parts.extend([docstring, ""])
        parts.append(source_span(source_lines, node))
        chunks.append(
            {
                "chunk_id": f"function:{relative}::{node.name}",
                "source_path": relative,
                "kind": "function",
                "text": "\n".join(parts).rstrip() + "\n",
                "score": 0.0,
            }
        )
    return chunks


def test_chunks(relative: str, tree: ast.Module, source_lines: list[str]) -> list[dict]:
    chunks: list[dict] = []
    for node in top_level_functions(tree):
        if not node.name.startswith("test"):
            continue
        chunks.append(
            {
                "chunk_id": f"test:{relative}::{node.name}",
                "source_path": relative,
                "kind": "test",
                "text": f"`{relative}::{node.name}`\n\n{source_span(source_lines, node)}\n",
                "score": 0.0,
            }
        )
    return chunks


def convention_chunks() -> list[dict]:
    path = KNOWLEDGE / "conventions.md"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    sections: list[tuple[str, list[str]]] = []
    heading = "Conventions"
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if body:
                sections.append((heading, body))
            heading = line[3:].strip()
            body = []
        else:
            body.append(line)
    if body:
        sections.append((heading, body))

    chunks: list[dict] = []
    for heading, lines in sections:
        content = "\n".join(lines).strip()
        if not content:
            continue
        slug = heading.lower().replace(" ", "-")
        chunks.append(
            {
                "chunk_id": f"convention:{slug}",
                "source_path": "knowledge/conventions.md",
                "kind": "convention",
                "text": f"Convention — {heading}\n\n{content}\n",
                "score": 0.0,
            }
        )
    return chunks


def fix_note_chunks() -> list[dict]:
    """One note per dev fixture: what was wrong and where, never how it was fixed."""
    root = FIXTURES / "dev"
    if not root.is_dir():
        return []
    chunks: list[dict] = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        defect_file = directory / "defect.json"
        if not defect_file.is_file():
            continue
        defect = json.loads(defect_file.read_text(encoding="utf-8"))
        modules = ", ".join(defect["allowed_paths"])
        chunks.append(
            {
                "chunk_id": f"fix_note:{defect['defect_id']}",
                "source_path": modules,
                "kind": "fix_note",
                "text": (
                    f"Previously repaired defect {defect['defect_id']}\n\n"
                    f"Category: {defect['category']}\n"
                    f"Module: {modules}\n"
                    f"Symptom: {defect['summary']}\n"
                ),
                "score": 0.0,
            }
        )
    return chunks


def build() -> list[dict]:
    chunks: list[dict] = []

    for path in sorted(TARGET_APP.glob("*.py")):
        relative = path.name
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines(keepends=True)
        tree = ast.parse(source, filename=relative)
        chunks.append(module_chunk(path, relative, tree))
        chunks.extend(function_chunks(relative, tree, lines))

    tests_dir = TARGET_APP / "tests"
    if tests_dir.is_dir():
        for path in sorted(tests_dir.glob("*.py")):
            relative = f"tests/{path.name}"
            source = path.read_text(encoding="utf-8")
            lines = source.splitlines(keepends=True)
            tree = ast.parse(source, filename=relative)
            chunks.extend(test_chunks(relative, tree, lines))

    chunks.extend(convention_chunks())
    chunks.extend(fix_note_chunks())

    chunks.sort(
        key=lambda chunk: (KIND_ORDER[chunk["kind"]], chunk["source_path"], chunk["chunk_id"])
    )
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file is out of date")
    args = parser.parse_args()

    chunks = build()
    rendered = "".join(
        json.dumps(chunk, ensure_ascii=False, sort_keys=True) + "\n" for chunk in chunks
    )

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != rendered:
            print("knowledge/chunks.jsonl is out of date; run scripts/build_knowledge.py")
            return 1
        print(f"knowledge/chunks.jsonl is up to date ({len(chunks)} chunks)")
        return 0

    KNOWLEDGE.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")

    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk["kind"]] = counts.get(chunk["kind"], 0) + 1
    for kind, count in sorted(counts.items()):
        print(f"  {kind:<12} {count}")
    print(f"{len(chunks)} chunks written to {OUTPUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
