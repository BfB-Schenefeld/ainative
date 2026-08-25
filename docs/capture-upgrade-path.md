# Capturing the AI-Native SAFe upgrade path

**The upgrade path is not a Rise 360 course.** It is a Vite/React single-page app
served from a public static host, embedded in the Scaled Agile LMS through a chain of
iframes. Its content is code-split into per-lesson JavaScript chunks under `/assets/`,
all of which are **plain public files with no authentication**.

That makes capture far easier than the Rise procedure in `capture-rise.md`: you do not
need a HAR at all once you know the chunk filenames. You need the HAR exactly once, to
discover them.

## 1. Capture a HAR

DevTools → Network → tick **Preserve log** and **Disable cache** → hard reload → click
through every lesson and open the quiz → Export button → **Export HAR (sanitized)**.
Details in `capture-rise.md` steps 1–4.

## 2. Take the assets out of the HAR

**Do not download the chunks.** A HAR saved with content already holds every response
body, and bundle filenames are content-hashed: a redeploy 404s them within minutes. The
HAR copy cannot go stale. This was learned the hard way — see ADR-0003.

```bash
# which origin is serving the app?
python3 tools/extract_assets_from_har.py capture.har --list
```

The content app is **not** the origin you browsed to. Look for a third-party host
serving a pile of hash-named `.js` files — for the AI-Native upgrade path that was
`ai-native-safe-upgrade-path.replit.app`. Ignore the LMS origin entirely.

```bash
python3 tools/extract_assets_from_har.py capture.har \
    --origin <that-host> --out chunks/
```

Every asset lands in `chunks/` with a `manifest.json` recording URL, sha256 and byte
count. The tool names any quiz chunks it spots.

**If it warns that a response had no body**, DevTools dropped it from its buffer. That
one URL does need refetching, and it needs refetching *now*, before the next deploy:

```bash
curl -sO "<the url from manifest.json>"
```

A downloaded file that comes back as HTML starting `<!DOCTYPE html>` is the SPA's
404 fallback served with status 200 — the chunk is already gone. Recapture the HAR.

## 3. Extract the quiz

```bash
python3 tools/extract_upgrade_path.py FinalQuiz-DUvUYCnK.js \
    --source-id "src:2026-08-26/upgrade-path-final-quiz" \
    --source-dir sources/ai-native-upgrade-path/2026-08-26-final-quiz \
    --quiz-dir knowledge/courses/ai-native-safe-overview/quiz \
    --course "course:scaledagile/ai-native-safe-overview" \
    --course-file knowledge/courses/ai-native-safe-overview/course.yaml \
    --url "https://<the-app-origin>/assets/FinalQuiz-DUvUYCnK.js"

python3 tools/validate.py
python3 tools/build_index.py
```

This writes one YAML file per question with `answer_status: confirmed`, every option
flagged correct or not, the app's own feedback text for **every** option including the
wrong ones, and a link to the lesson each question is drawn from.

## Why this works

The quiz is graded client-side. The React component receives the whole question bank
with `correctAnswer` and `optionFeedback` already attached, then renders a random draw
from it. Nothing is fetched at grading time, so the answer key has to be in the bundle.

## Reading other chunks

Lesson chunks hold their prose as JSX rather than a data literal, so
`extract_upgrade_path.py` does not apply. Use the generic parser to look around:

```bash
python3 tools/js_object.py Lesson3-XXXX.js --find SOME_EXPORT
```

and check what a chunk exports with:

```bash
grep -o 'export{[^}]*}' Lesson3-XXXX.js
```

Anything exported as a data literal (`const x=[{...}]`) parses directly. Prose embedded
in `t.jsx(r,{text:"..."})` calls needs a small JSX-aware extractor — not written yet.

## Rights

The chunks being public and unauthenticated does not make the content unlicensed. Same
`rights.redistribution: none` applies as everywhere else in `sources/`. See `NOTICE.md`.
