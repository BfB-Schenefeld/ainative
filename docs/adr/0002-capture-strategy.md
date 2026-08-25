# ADR 0002 — Capture strategy: stop using full-page HTML exports

**Status:** accepted · 2026-08-25 — mechanism partly superseded by [ADR-0003](0003-not-a-rise-course.md);
the conclusion (stop using full-page exports) holds, the Rise diagnosis does not

## Context
The first capture (`src:2026-08-25/learning-plans-exams`) is an 8.5 MB SingleFile export
of the Scaled Agile "Learning Plans & Exams" page. Analysis found:

- The content sits six iframes deep, each level in a `srcdoc` attribute.
- 8.3 MB of the 8.5 MB is base64 fonts, CSS and icons. The actual course DOM is 64 KB.
- The innermost frame is an Articulate Rise 360 course, which holds all lessons and the
  full quiz bank in a JS payload and renders one lesson at a time.
- SingleFile strips JavaScript. The export therefore contains the Welcome lesson and the
  lesson menu, and nothing else. No questions. No answers.

Extrapolated: covering one 8-lesson course this way costs ~8 exports and ~68 MB of
captures to recover ~100 KB of knowledge, and still misses anything behind an
interaction (accordion, flip card, knowledge check) that was not clicked open before saving.

## Decision
1. Treat full-page HTML exports as the fallback, not the default.
2. Prefer the Rise 360 course JSON payload, grabbed from the Network tab. One file per
   course, complete, including quiz stems, options and answer keys.
3. Keep `tools/extract_singlefile.py` for exports already taken and for pages that are
   not Rise courses (learning plan lists, exam result pages, framework articles).
4. Always commit the stripped capture, never the raw one; record the original sha256.

## Consequences
- Capture step now requires DevTools rather than a browser extension click.
- A second extractor (`tools/extract_rise.py`) is needed and is not yet written.
- Repo stays small: ~200 KB per capture instead of ~8 MB.
