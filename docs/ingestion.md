# Ingestion runbook

## 0. Know what a SingleFile export actually contains

The Scaled Agile learning pages are Salesforce Experience Cloud pages that embed an
LMS shell that embeds an Articulate Rise 360 course, six frames deep:

```
root
└─ resizable-iframe            (LMS)
   └─ iFramePlayer
      └─ launcher-content
         └─ content_frame
            └─ dispatch-frame  (Rise 360 course DOM)  ← the content
```

Rise 360 keeps the **entire** course — every lesson, every quiz question, every answer
option — in a JavaScript payload and renders one lesson at a time. SingleFile strips
JavaScript. So:

> **One SingleFile export = one visible lesson. Nothing more.**

The 2026-08-25 capture yielded the Welcome page and the lesson menu. Lessons 1–6, the
Final Quiz and the References are named in the menu but their content is not in the
file. See `docs/adr/0002-capture-strategy.md` for what to do instead.

## 1. Capture

Preferred, in order:

1. **Rise course JSON** — open the course, DevTools → Network → filter `course` or
   `.json`, save the payload. One file, whole course, questions and answers included.
   Drop it in `sources/<provider>/<date>-<slug>/raw/` and write a small extractor.
2. **One SingleFile export per lesson**, with *Save shadow DOM* and
   *Save raw page* enabled in SingleFile settings.
3. Whatever you have. Partial is fine, `capture_status` records it.

## 2. Extract

```bash
python3 tools/extract_singlefile.py <capture>.html \
    --out sources/scaledagile-community/<YYYY-MM-DD>-<slug> \
    --source-id "src:<YYYY-MM-DD>/<slug>"
```

Writes `raw/page.stripped.html.gz`, `raw/content-frame.html`, `extracted.json`.
Base64 fonts/images are replaced with a placeholder — the 8.5 MB capture becomes
~200 KB of committed bytes. The original file's sha256 is recorded so the capture is
still verifiable if you keep the original elsewhere.

Then hand-write `source.yaml` next to it (provenance, licence, coverage notes).

## 3. Curate

Turn blocks into knowledge records. Rules:

- Every record cites at least one `src:...#bNNNN`.
- Verbatim provider prose goes in `body` only where it carries the meaning; otherwise
  paraphrase. Keep `verbatim: true` on records that quote directly.
- Mint concepts eagerly, merge later. A concept with one reference is fine.
- Do not invent quiz answers. If a question was captured without its key,
  `answer_status: unknown`.

## 4. Validate

```bash
python3 tools/validate.py     # schema + referential integrity, exits non-zero on error
python3 tools/build_index.py  # writes index/ (gitignored)
```

CI runs both on every push and PR.
