#!/usr/bin/env python3
"""
scan_har.py -- find the course data payload inside a DevTools HAR export.

You don't need to know which network request holds the course. Save the whole HAR
with content, point this at it, and it ranks every response body by how course-shaped
it looks.

Usage:
    python3 tools/scan_har.py capture.har                 # rank candidates
    python3 tools/scan_har.py capture.har --dump OUTDIR   # write the top candidates out

HAR files contain cookies, auth headers and bearer tokens. Never commit one.
`*.har` is gitignored.
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import sys
from collections import Counter

# Markers that suggest Articulate Rise / quiz content rather than app chrome.
MARKERS = [
    "correctResponse", "correct_response", "isCorrect", "correct",
    "quiz", "question", "answers", "choices", "distractor",
    "lessons", "lessonId", "blockId", "items",
    "rise", "articulate", "knowledgeCheck", "feedback",
]
STRONG = {"correctResponse", "isCorrect", "knowledgeCheck", "distractor", "blockId"}


def body_of(entry) -> str | None:
    content = entry.get("response", {}).get("content", {})
    text = content.get("text")
    if not text:
        return None
    if content.get("encoding") == "base64":
        try:
            text = base64.b64decode(text).decode("utf-8", errors="replace")
        except Exception:
            return None
    return text


def score(text: str) -> tuple[int, Counter]:
    hits = Counter()
    for m in MARKERS:
        n = len(re.findall(rf"\b{re.escape(m)}\b", text))
        if n:
            hits[m] = n
    pts = sum(hits.values())
    pts += 500 * sum(1 for m in hits if m in STRONG)
    return pts, hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("har")
    ap.add_argument("--dump", help="directory to write top candidates into")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--min-bytes", type=int, default=5000)
    args = ap.parse_args()

    har = json.loads(pathlib.Path(args.har).read_text(encoding="utf-8", errors="replace"))
    entries = har.get("log", {}).get("entries", [])
    print(f"{len(entries)} requests in HAR\n", file=sys.stderr)

    rows = []
    for i, e in enumerate(entries):
        text = body_of(e)
        if not text or len(text) < args.min_bytes:
            continue
        pts, hits = score(text)
        if pts == 0:
            continue
        rows.append({
            "i": i,
            "url": e["request"]["url"],
            "mime": e["response"].get("content", {}).get("mimeType", ""),
            "bytes": len(text),
            "score": pts,
            "hits": hits,
            "text": text,
        })

    rows.sort(key=lambda r: (-r["score"], -r["bytes"]))
    if not rows:
        print("No course-shaped responses found. Did you save the HAR *with content*, "
              "and did you click through at least one lesson and the quiz before saving?")
        return 1

    for r in rows[: args.top]:
        top_hits = ", ".join(f"{k}x{v}" for k, v in r["hits"].most_common(6))
        print(f"[{r['i']:>4}] score={r['score']:<6} {r['bytes']:>9,}B  {r['mime'][:28]:<28} {r['url'][:100]}")
        print(f"        {top_hits}")

    if args.dump:
        out = pathlib.Path(args.dump)
        out.mkdir(parents=True, exist_ok=True)
        for r in rows[: args.top]:
            ext = "json" if "json" in r["mime"] else "js" if "javascript" in r["mime"] else "txt"
            p = out / f"{r['i']:04d}-score{r['score']}.{ext}"
            p.write_text(r["text"], encoding="utf-8")
        print(f"\nwrote {min(args.top, len(rows))} candidates to {out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
