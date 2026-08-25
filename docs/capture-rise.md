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

Right-click anywhere in the request list → **Save all as HAR with content**.

The "**with content**" part is mandatory. Plain "Save as HAR" in some browsers omits
response bodies and you get a useless index of URLs.

Firefox: right-click → *Save All As HAR*. Safari: enable the Develop menu, then
*Export HAR* from the Network tab's export button.

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

## Security

**HAR files contain your session cookies and bearer tokens.** Anyone with the HAR can
log in as you until those expire. `*.har` is in `.gitignore`. Keep them local, delete
them once the payload is extracted, and never attach one to an issue or a chat.

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
