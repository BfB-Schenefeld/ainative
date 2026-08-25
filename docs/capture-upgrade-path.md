# Capturing the AI-Native SAFe upgrade path

**The upgrade path is not a Rise 360 course.** It is a Vite/React single-page app
served from a public static host, embedded in the Scaled Agile LMS through a chain of
iframes. Its content is code-split into per-lesson JavaScript chunks under `/assets/`,
all of which are **plain public files with no authentication**.

That makes capture far easier than the Rise procedure in `capture-rise.md`: you do not
need a HAR at all once you know the chunk filenames. You need the HAR exactly once, to
discover them.

## 1. Get the chunk filenames (once per app build)

Filenames are content-hashed (`FinalQuiz-DUvUYCnK.js`) and change on every redeploy, so
they cannot be hardcoded. Two ways to list them:

**From a HAR** you already captured (see `capture-rise.md` steps 1–4):

```bash
python3 - <<'PY'
import json, re
har = json.load(open("community.scaledagile.com.har", encoding="utf-8"))
for e in har["log"]["entries"]:
    u = e["request"]["url"]
    if "/assets/" in u and u.endswith(".js"):
        print(e["response"]["content"].get("size", 0), u)
PY
```

**From the app itself**, which is simpler if you have the origin: open the upgrade path,
DevTools → Network → filter `.js`, and read the filenames. Or fetch the app's
`index.html` and read the `<script type="module" src="/assets/index-*.js">` entry; the
index chunk imports everything else and the import specifiers are the full manifest.

## 2. Download the chunks

```bash
BASE=https://<the-app-origin>/assets
curl -sO "$BASE/FinalQuiz-DUvUYCnK.js"
# ...and one per lesson chunk
```

No cookies, no headers, no session. These are static assets.

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
