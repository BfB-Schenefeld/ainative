#!/usr/bin/env python3
"""
extract_singlefile.py -- normalize a SingleFile HTML capture into structured JSON.

The Scaled Agile community pages nest the actual learning content inside a chain
of `<iframe srcdoc="...">` elements (Experience Cloud -> LMS shell -> launcher ->
content frame -> Rise 360 course). This tool unwraps that chain, strips embedded
base64 assets, and emits a flat, ordered list of content blocks with provenance.

Usage:
    python3 tools/extract_singlefile.py CAPTURE.html --out DIR [--source-id ID]

Outputs into DIR:
    raw/page.stripped.html.gz   full page, data: URIs replaced by placeholders
    raw/content-frame.html      deepest iframe (the actual course DOM)
    extracted.json              normalized blocks + frame chain + provenance
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pathlib
import re
import sys
from datetime import datetime, timezone

from bs4 import BeautifulSoup

EXTRACTOR_VERSION = "0.1.0"

DATA_URI_RE = re.compile(r"data:[a-z][a-z0-9/+.-]*;base64,[A-Za-z0-9+/=]{200,}")
SAVED_URL_RE = re.compile(r"url:\s*(\S+)")
SAVED_DATE_RE = re.compile(r"saved date:\s*(.+)")

BLOCK_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "figcaption", "td", "th"]
NOISE = {
    "skip to content",
    "full screen mode",
    "reset",
    "progress",
    "menu",
    "open in new tab",
    "expand search",
    "shopping cart",
    "skip to main content",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strip_data_uris(html: str) -> str:
    return DATA_URI_RE.sub("data:REDACTED-BASE64-ASSET", html)


def unwrap_frames(html: str):
    """Return [(path, html), ...] for the document and every nested srcdoc frame."""
    chain = [("root", html)]
    current = html
    path = "root"
    while True:
        soup = BeautifulSoup(current, "lxml")
        nxt = None
        for frame in soup.find_all("iframe"):
            srcdoc = frame.get("srcdoc")
            if srcdoc and len(srcdoc) > 2000:  # skip trackers / chat widgets
                nxt = (f"{path}>{frame.get('id') or 'iframe'}", srcdoc)
                break
        if not nxt:
            return chain
        chain.append(nxt)
        path, current = nxt


def text_of(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def extract_blocks(html: str, frame_path: str, start_idx: int):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    for frame in soup.find_all("iframe"):
        frame.decompose()

    blocks = []
    seen = set()
    idx = start_idx
    for node in soup.find_all(BLOCK_TAGS):
        # keep leaf-most blocks only
        if node.find(BLOCK_TAGS):
            continue
        txt = text_of(node)
        if not txt or txt.lower() in NOISE or len(txt) < 2:
            continue
        key = (node.name, txt)
        if key in seen:
            continue
        seen.add(key)
        kind = {
            "li": "list_item",
            "p": "paragraph",
            "blockquote": "quote",
            "figcaption": "caption",
            "td": "cell",
            "th": "cell",
        }.get(node.name, "heading")
        block = {
            "id": f"b{idx:04d}",
            "type": kind,
            "text": txt,
            "frame": frame_path,
        }
        if kind == "heading":
            block["level"] = int(node.name[1])
        blocks.append(block)
        idx += 1
    return blocks, idx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("--out", required=True)
    ap.add_argument("--source-id", default=None)
    args = ap.parse_args()

    src = pathlib.Path(args.capture)
    out = pathlib.Path(args.out)
    (out / "raw").mkdir(parents=True, exist_ok=True)

    raw_bytes = src.read_bytes()
    html = raw_bytes.decode("utf-8", errors="replace")

    url = (SAVED_URL_RE.search(html[:4000]) or [None, None])[1]
    saved = (SAVED_DATE_RE.search(html[:4000]) or [None, None])[1]

    stripped = strip_data_uris(html)
    with gzip.open(out / "raw" / "page.stripped.html.gz", "wt", encoding="utf-8") as fh:
        fh.write(stripped)

    chain = unwrap_frames(stripped)
    (out / "raw" / "content-frame.html").write_text(chain[-1][1], encoding="utf-8")

    blocks, idx = [], 1
    for path, frame_html in chain:
        got, idx = extract_blocks(frame_html, path, idx)
        blocks.extend(got)

    doc = {
        "source_id": args.source_id or src.stem,
        "schema": "schemas/source.schema.json",
        "extractor": {"name": "extract_singlefile.py", "version": EXTRACTOR_VERSION},
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capture": {
            "original_filename": src.name,
            "url": url,
            "saved_at_raw": saved,
            "bytes": len(raw_bytes),
            "sha256": sha256(raw_bytes),
        },
        "frame_chain": [{"path": p, "bytes": len(h)} for p, h in chain],
        "blocks": blocks,
    }
    (out / "extracted.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"frames={len(chain)} blocks={len(blocks)} -> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
