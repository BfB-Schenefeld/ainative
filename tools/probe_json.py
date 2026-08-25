#!/usr/bin/env python3
"""
probe_json.py -- map the shape of an unknown course payload and pull quiz-shaped nodes.

Rise 360's internal JSON schema is not documented and changes between versions. Rather
than guess it, this walks the payload, reports its structure, and extracts every node
that looks like a question so you can see what you actually got.

Usage:
    python3 tools/probe_json.py payload.json            # structure report
    python3 tools/probe_json.py payload.json --quiz     # candidate questions as JSON
    python3 tools/probe_json.py payload.js  --unwrap    # strip a `window.X = {...};` wrapper

Once the shape is known, write a proper extractor for it and delete the guesswork.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter

QUESTION_KEYS = {"question", "prompt", "stem", "title", "text", "questionText"}
OPTION_KEYS = {"answers", "options", "choices", "responses", "distractors"}
CORRECT_KEYS = {"correct", "isCorrect", "correctResponse", "correct_response", "isRight"}


def unwrap(text: str) -> str:
    """Strip a JS assignment wrapper: window.__DATA__ = {...};"""
    text = text.strip()
    m = re.match(r"^[^=]{0,200}=\s*(.*?);?\s*$", text, re.S)
    if m and m.group(1).lstrip().startswith(("{", "[")):
        return m.group(1)
    return text


def walk(node, path="$", depth=0, shapes=None, maxdepth=8):
    if shapes is None:
        shapes = Counter()
    if depth > maxdepth:
        return shapes
    if isinstance(node, dict):
        shapes[f"{path} {{{','.join(sorted(node)[:8])}}}"] += 1
        for k, v in node.items():
            walk(v, f"{path}.{k}", depth + 1, shapes, maxdepth)
    elif isinstance(node, list):
        shapes[f"{path}[] n={len(node)}"] += 1
        for v in node[:3]:
            walk(v, f"{path}[]", depth + 1, shapes, maxdepth)
    return shapes


def find_quiz(node, path="$", out=None):
    if out is None:
        out = []
    if isinstance(node, dict):
        keys = set(node)
        has_opts = keys & OPTION_KEYS
        has_stem = keys & QUESTION_KEYS
        if has_opts and has_stem:
            out.append({"path": path, "node": node})
        else:
            # also catch option lists whose members carry a correctness flag
            for k in has_opts:
                v = node.get(k)
                if isinstance(v, list) and any(isinstance(o, dict) and set(o) & CORRECT_KEYS for o in v):
                    out.append({"path": path, "node": node})
                    break
        for k, v in node.items():
            find_quiz(v, f"{path}.{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            find_quiz(v, f"{path}[{i}]", out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("payload")
    ap.add_argument("--quiz", action="store_true", help="dump candidate question nodes")
    ap.add_argument("--unwrap", action="store_true", help="strip a JS assignment wrapper first")
    ap.add_argument("--maxdepth", type=int, default=6)
    args = ap.parse_args()

    text = pathlib.Path(args.payload).read_text(encoding="utf-8", errors="replace")
    if args.unwrap:
        text = unwrap(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"Not valid JSON ({e}). Try --unwrap, or the payload may be encoded/minified JS.", file=sys.stderr)
        return 1

    if args.quiz:
        hits = find_quiz(data)
        print(json.dumps(hits, indent=2, ensure_ascii=False))
        print(f"\n{len(hits)} candidate question nodes", file=sys.stderr)
        return 0

    shapes = walk(data, maxdepth=args.maxdepth)
    for shape, n in shapes.most_common(60):
        print(f"{n:>5}  {shape[:160]}")
    print(f"\n{len(find_quiz(data))} candidate question nodes (run with --quiz)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
