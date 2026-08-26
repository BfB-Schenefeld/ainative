#!/usr/bin/env python3
"""
extract_assets_from_har.py -- pull bundle chunks out of a HAR, no network needed.

A HAR saved "with content" already holds every response body. Downloading the same
files afterwards is both unnecessary and a race: bundle filenames are content-hashed,
so a redeploy makes them 404 (see docs/adr/0003-not-a-rise-course.md). Take the bodies
from the HAR instead — they cannot go stale.

Usage:
    # see which origins served JS/CSS assets
    python3 tools/extract_assets_from_har.py capture.har --list

    # dump everything from one origin
    python3 tools/extract_assets_from_har.py capture.har \\
        --origin ai-native-safe-upgrade-path.replit.app --out chunks/

Writes each asset under <out>/ plus a manifest.json recording URL, sha256, byte count
and whether the HAR actually carried a body.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import pathlib
import sys
from collections import defaultdict
from urllib.parse import urlparse

ASSET_EXT = (".js", ".mjs", ".css", ".json")


def body_of(entry):
    content = entry.get("response", {}).get("content", {})
    text = content.get("text")
    if text is None:
        return None
    if content.get("encoding") == "base64":
        try:
            return base64.b64decode(text)
        except Exception:
            return None
    return text.encode("utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("har")
    ap.add_argument("--list", action="store_true", help="summarize origins and exit")
    ap.add_argument("--origin", action="append", default=[], help="hostname to extract (repeatable)")
    ap.add_argument("--out", default="chunks")
    ap.add_argument("--all-types", action="store_true", help="extract every response, not just JS/CSS/JSON")
    ap.add_argument("--show-raw", metavar="TEXT",
                    help="print the raw bytes of the HAR file around the first occurrence "
                         "of TEXT, exactly as stored. Shows the JSON escaping for yourself.")
    args = ap.parse_args()

    har_path = pathlib.Path(args.har)

    if args.show_raw:
        blob = har_path.read_bytes()
        needle = args.show_raw.encode("utf-8")
        at = blob.find(needle)
        if at < 0:
            print(f"{args.show_raw!r} not found as raw bytes.\n"
                  "If it contains quotes, umlauts, dashes or curly quotes, the HAR stores "
                  "them escaped (\\\" and \\uXXXX). Search a plain-ASCII fragment instead.",
                  file=sys.stderr)
            return 1
        lo, hi = max(0, at - 220), min(len(blob), at + 520)
        print(f"file: {har_path.name}   size: {len(blob):,} bytes   match at byte offset {at:,}\n")
        print("--- raw bytes, verbatim ---")
        print(blob[lo:hi].decode("utf-8", errors="replace"))
        print("--- end ---")
        return 0

    har = json.loads(har_path.read_text(encoding="utf-8", errors="replace"))
    entries = har.get("log", {}).get("entries", [])

    if args.list:
        stats = defaultdict(lambda: {"assets": 0, "bytes": 0, "with_body": 0, "total": 0})
        for e in entries:
            host = urlparse(e["request"]["url"]).netloc
            s = stats[host]
            s["total"] += 1
            path = urlparse(e["request"]["url"]).path
            if path.endswith(ASSET_EXT):
                s["assets"] += 1
                b = body_of(e)
                if b:
                    s["with_body"] += 1
                    s["bytes"] += len(b)
        print(f"{'origin':<52} {'reqs':>5} {'assets':>7} {'bodies':>7} {'bytes':>12}")
        for host, s in sorted(stats.items(), key=lambda kv: -kv[1]["bytes"]):
            print(f"{host[:52]:<52} {s['total']:>5} {s['assets']:>7} {s['with_body']:>7} {s['bytes']:>12,}")
        print("\nThe content app is usually NOT the origin you browsed to — look for a "
              "third-party host serving a pile of hash-named .js files.", file=sys.stderr)
        return 0

    if not args.origin:
        print("No --origin given. Run with --list first to see the candidates.", file=sys.stderr)
        return 1

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest, seen, missing = [], set(), 0

    for e in entries:
        url = e["request"]["url"]
        parts = urlparse(url)
        if parts.netloc not in args.origin:
            continue
        if not args.all_types and not parts.path.endswith(ASSET_EXT):
            continue
        name = pathlib.PurePosixPath(parts.path).name or "index.html"
        if name in seen:
            continue
        body = body_of(e)
        rec = {
            "url": url,
            "filename": name,
            "status": e.get("response", {}).get("status"),
            "mime": e.get("response", {}).get("content", {}).get("mimeType", ""),
            "started": e.get("startedDateTime"),
            "body_present": body is not None,
        }
        if body is None:
            missing += 1
            rec["note"] = "no body in HAR (DevTools buffer dropped it) — refetch this URL now"
        else:
            (out / name).write_bytes(body)
            rec["bytes"] = len(body)
            rec["sha256"] = hashlib.sha256(body).hexdigest()
            seen.add(name)
        manifest.append(rec)

    (out / "manifest.json").write_text(
        json.dumps({"har": pathlib.Path(args.har).name, "origins": args.origin,
                    "assets": manifest}, indent=2) + "\n", encoding="utf-8")

    print(f"{len(seen)} assets written to {out}/", file=sys.stderr)
    if missing:
        print(f"WARNING: {missing} responses had no body in the HAR. Refetch those URLs "
              f"immediately — see manifest.json.", file=sys.stderr)
    quiz = [m["filename"] for m in manifest if "quiz" in m["filename"].lower()]
    if quiz:
        print(f"quiz chunks: {', '.join(quiz)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
