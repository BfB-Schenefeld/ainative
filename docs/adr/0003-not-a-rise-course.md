# ADR 0003 — The upgrade path is a static SPA, not a Rise 360 course

**Status:** accepted · 2026-08-26 · supersedes the mechanism assumed in ADR-0002

## Context
ADR-0002 inferred from the iframe chain (`dispatch-frame`, `launcher-content`) that the
innermost frame was an Articulate Rise 360 course delivered by Dispatch, and prescribed
a HAR capture to recover the Rise boot payload.

A HAR of `community.scaledagile.com` (399 requests) showed otherwise. `scan_har.py`
ranked the top candidates and the decisive entry was:

```
[388] score=49  42,852B  text/javascript
      https://ai-native-safe-upgrade-path.replit.app/assets/FinalQuiz-DUvUYCnK.js
      questionx31, quizx11, itemsx4, feedbackx2, answersx1
```

The higher-scoring entries above it were all Salesforce platform bundles and SLDS
stylesheets — false positives, since `items`, `question` and `correct` are common
identifiers in framework code. **Score rank was not truth rank**; the origin was.

The upgrade path is a Vite/React SPA on a public static host, code-split into per-lesson
chunks. `FinalQuiz-*.js` contains the entire question bank as a JS object literal:
`question`, `options`, `correctAnswer`, and `optionFeedback` for every option, right and
wrong, plus a map from each question to the lesson it is drawn from.

## Decision
1. Capture the upgrade path by downloading bundle chunks directly. No HAR, no auth, no
   cookies. `docs/capture-upgrade-path.md` is the procedure.
2. Keep the HAR step, reduced to a one-off: it is how the app origin and the
   content-hashed chunk filenames get discovered, and filenames change on every redeploy.
3. Parse the chunks with `tools/js_object.py` — bundle data is a JS object literal, not
   JSON, so `json.loads` cannot read it.
4. `scan_har.py` stays useful but its output is a shortlist to read, not an answer.
   Weight the origin over the score.

## Consequences
- The full 30-question bank with confirmed answer keys is recoverable in one command.
- The Rise procedure in `capture-rise.md` remains valid for genuine Rise courses
  (*Adopting AI-Native SAFe* has not been inspected yet) but does not apply here.
- Lesson prose lives in JSX calls rather than data literals, so recovering lesson bodies
  still needs a JSX-aware extractor. Not written.
- Chunk filenames are build-scoped. Source records must capture the exact URL, because
  the same path will 404 after the next deploy.
