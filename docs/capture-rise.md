# Capturing a Rise 360 course properly

Full-page HTML export gives you one lesson. This gives you the whole course, quiz
answer keys included. Budget 10 minutes the first time, 2 minutes after that.

## Why this works

Rise 360 is a client-side app. It downloads the entire course — every lesson, every
quiz question, every option and which option is correct — as one payload, then renders
one lesson at a time and grades the quiz **in the browser**. That means the answer key
is already on your machine the moment the course finishes loading. You are not
extracting anything you weren't sent; you're just keeping it.

SingleFile strips JavaScript, which is why the export threw all of it away.

---

## The method: save a HAR

A HAR is a JSON log of every network request *and response body* on a page. Save one,
and you have the payload without needing to identify which request it was.

### 1. Open DevTools before the course loads

Open the course page. Press **F12** (or `Ctrl+Shift+I`, `Cmd+Opt+I` on Mac).
Go to the **Network** tab.

Tick both:
- **Preserve log**
- **Disable cache**

If you skip *Disable cache*, a second visit serves the payload from cache and it never
appears in the log. This is the single most common failure.

### 2. Hard reload

`Ctrl+Shift+R` (`Cmd+Shift+R`). Wait for the course to fully render.

### 3. Click through everything you want

The boot payload usually contains the whole course, but not always — some
configurations lazy-load per lesson, and some quiz banks load only when the quiz opens.
So before saving:

- Open each lesson in the menu, top to bottom.
- **Open the Final Quiz and let the first question render.** Do not answer it.
- Expand any accordions, flip cards or knowledge checks you pass.

Everything that loads lands in the log. Over-clicking costs nothing.

### 4. Export

Click the **download arrow** in the Network panel action bar: **Export HAR (sanitized)**.

That is the correct button. Chrome 130 renamed the old "Save all as HAR with content";
if you are looking for that label you will not find it.

**Sanitized only strips headers** — `Cookie`, `Set-Cookie`, `Authorization`. Response
bodies are fully included, which is the only part we need. There is also an
"Export HAR (with sensitive data)" variant behind
*Settings → Preferences → Network → Allow to generate HAR with sensitive data*, then a
long-press on the Export button. **Do not use it.** It exists for debugging auth
failures and it would put your session tokens in the file for no benefit.

Firefox: gear icon → *Save All As HAR*. Safari: enable the Develop menu, then export
from the Network tab.

Expect 5–50 MB. That's fine, it's a working file and never gets committed.

### 5. Find the payload

```bash
python3 tools/scan_har.py course.har
```

Ranks every response body by how course-shaped it is — it counts markers like
`correctResponse`, `isCorrect`, `blockId`, `lessons`, `distractor`. The real payload
usually wins by orders of magnitude.

```bash
python3 tools/scan_har.py course.har --dump /tmp/candidates
```

### 6. Confirm you got the answers

```bash
python3 tools/probe_json.py /tmp/candidates/0042-score3210.json --quiz
```

If that prints question nodes with `correct: true` on one of the options, you have the
whole thing. Structure report without `--quiz`. If the file is JS rather than JSON
(`window.__something = {...};`) add `--unwrap`.

### 7. Ingest

Put the *payload* — not the HAR — in
`sources/scaledagile-community/<date>-<slug>/raw/`, write the `source.yaml`, and write
a `tools/extract_rise.py` matching the shape `probe_json.py` just showed you. Then the
normal `validate.py` / `build_index.py` cycle applies.

---

## If scan_har.py comes up empty

DevTools drops response bodies for very large resources once its buffer fills, so the
payload can be listed in the HAR with no `content.text`. Grab that one request directly
instead: sort the Network list by **Size** descending, find the outlier, right-click →
**Copy → Copy response**, paste into a file, and run `probe_json.py` on that.

Other causes, in order of likelihood: *Disable cache* was not ticked; the export
happened before the course finished loading; the quiz was never opened.

## Security

Sanitized HAR export strips `Cookie`, `Set-Cookie` and `Authorization` headers, so a
sanitized file is not a session-hijacking risk. It can still contain account
identifiers, request bodies and response bodies with personal data. `*.har` is in
`.gitignore` regardless — HARs are working files, not artifacts. Delete them once the
payload is extracted.

---

## If the HAR route fails

**Console, scoped to the course frame.** DevTools → Console → the context dropdown at
the top left (says "top"). Switch it to the `dispatch-frame` / course frame. Then:

```js
Object.keys(window).filter(k => /course|rise|data|content|lesson/i.test(k))
```

Follow whatever that turns up and `copy(JSON.stringify(window.THING))` — `copy()` puts
it straight on your clipboard.

**Failing that:** one SingleFile export per lesson, with *Save shadow DOM* and *Save raw
page* enabled in SingleFile's settings, and every interaction manually expanded before
each save. Slow, lossy, and it will not get you the answer keys — Rise never renders
them into the DOM until you answer. Last resort.

## What this doesn't cover

The learning-plan list itself (your enrolled courses, exam entitlements, attempt
history) is a Salesforce page, not a Rise course. `extract_singlefile.py` handles that
fine — full-page export is the right tool there.
