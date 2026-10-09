#!/usr/bin/env python3
"""
vidyard_captions.py -- download the publisher's own captions for Vidyard videos
and convert them to SRT.

The AI-Native ART Leader Trainer Enablement app embeds its videos through Vidyard
and the bundle carries each video's id. Vidyard's player endpoint,
https://play.vidyard.com/player/<videoId>.json, is public and lists a `captions`
array per chapter with a signed `vttUrl`. Those captions are the publisher's own,
so they beat speech-to-text on product terminology and need no transcription.

Usage:
    python vidyard_captions.py                 # all videos listed in VIDEOS
    python vidyard_captions.py --out subs      # into a subdirectory
    python vidyard_captions.py --lang en       # caption language, default en
    python vidyard_captions.py --keep-vtt      # also keep the raw .vtt
    python vidyard_captions.py --id ABC123 --name "My video"   # one ad-hoc video

Output filenames match the source video titles, so each .srt lands next to its .mp4.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

PLAYER = "https://play.vidyard.com/player/{}.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# videoId -> output name, taken from the app bundle's video catalogue
VIDEOS = [
    ("PaS7MCVcstas7c799ixiMu", "Using the learner companion app"),
    ("32AM2UqgyY5fRV4syhAByB", "Using the assessment tool"),
    ("gMb6nL95icb4XgidEEJEc7", "Assessing each success factor"),
    ("wAs8hpjyUhjM9Lr41F1VsL", "Resolving the gaps"),
    ("SbxYLWYZM8oRAyVDS55duP", "Managing long timeboxes"),
    ("wJ2He5Gzfckdo13nsiApNC", "Creating a launch plan"),
    ("Xiv4ejQ2YPJvNpYrnokFpM", "Communicating the launch plan"),
]

TS = re.compile(r"(\d{1,3}:)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})")
ARROW = re.compile(r"\s*-->\s*")
# inline VTT markup: <c.classname>, </c>, <v Speaker>, <00:00:01.000> karaoke cues
TAG = re.compile(r"</?[cvibu](?:\.[^>\s]+)?(?:\s[^>]*)?>|<\d{1,3}:\d{2}:\d{2}[.,]\d{1,3}>")
SKIP_BLOCK = re.compile(r"^(WEBVTT|NOTE|STYLE|REGION)\b")


def get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def norm_ts(raw: str) -> str | None:
    """VTT timestamp -> SRT HH:MM:SS,mmm. VTT may omit hours; SRT may not."""
    m = TS.fullmatch(raw.strip())
    if not m:
        return None
    h = int((m.group(1) or "0:")[:-1])
    mm, ss, ms = int(m.group(2)), int(m.group(3)), m.group(4).ljust(3, "0")[:3]
    return f"{h:02d}:{mm:02d}:{ss:02d},{ms}"


def vtt_to_srt(vtt: str) -> str:
    """Convert a WebVTT document to SRT.

    Drops the header and NOTE/STYLE/REGION blocks, discards cue identifiers and cue
    settings, strips inline markup, renumbers cues sequentially, and rewrites
    timestamps (VTT allows MM:SS.mmm; SRT requires HH:MM:SS,mmm).
    """
    vtt = vtt.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    out, n = [], 0
    for block in re.split(r"\n{2,}", vtt):
        block = block.strip("\n")
        if not block.strip() or SKIP_BLOCK.match(block.strip()):
            continue
        lines = block.split("\n")
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue  # no timing line: not a cue
        left, _, right = lines[ti].partition("-->")
        start = norm_ts(left)
        # cue settings ride on the end of the timing line, after the end timestamp
        end = norm_ts(right.strip().split()[0]) if right.strip() else None
        if not start or not end:
            continue
        text = "\n".join(TAG.sub("", l).rstrip() for l in lines[ti + 1:]).strip("\n")
        if not text.strip():
            continue
        n += 1
        out.append(f"{n}\n{start} --> {end}\n{text}\n")
    return "\n".join(out)


def pick_caption(payload: dict, lang: str):
    """Walk the player payload for a caption track in the wanted language."""
    found = []
    for ch in payload.get("chapters", []) or []:
        for cap in ch.get("captions", []) or []:
            if cap.get("vttUrl"):
                found.append(cap)
    if not found:
        return None, []
    exact = [c for c in found if (c.get("language") or "").lower() == lang.lower()]
    if exact:
        exact.sort(key=lambda c: (not c.get("isDefault"), c.get("languageIndex", 99)))
        return exact[0], found
    return None, found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--keep-vtt", action="store_true")
    ap.add_argument("--id", help="one ad-hoc video id instead of the built-in list")
    ap.add_argument("--name", help="output name for --id")
    args = ap.parse_args()

    videos = [(args.id, args.name or args.id)] if args.id else VIDEOS
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    ok = fail = 0
    for vid, name in videos:
        try:
            doc = json.loads(get(PLAYER.format(vid)))
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
            print(f"FAIL  {name}: player lookup failed: {e}")
            fail += 1
            continue
        payload = doc.get("payload") or doc
        cap, allcaps = pick_caption(payload, args.lang)
        if not cap:
            langs = ", ".join(sorted({c.get("language", "?") for c in allcaps})) or "none"
            print(f"SKIP  {name}: no '{args.lang}' captions (available: {langs})")
            fail += 1
            continue
        try:
            vtt = get(cap["vttUrl"]).decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError) as e:
            print(f"FAIL  {name}: caption download failed: {e}")
            fail += 1
            continue

        srt = vtt_to_srt(vtt)
        cues = srt.count(" --> ")
        if not cues:
            print(f"FAIL  {name}: caption file parsed to zero cues")
            fail += 1
            continue
        (out / f"{name}.srt").write_text(srt, encoding="utf-8")
        if args.keep_vtt:
            (out / f"{name}.vtt").write_text(vtt, encoding="utf-8")
        print(f"OK    {name}.srt  ({cues} cues, {len(srt):,} chars)")
        ok += 1

    print(f"\n{ok} written, {fail} failed")
    return 0 if ok and not fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
