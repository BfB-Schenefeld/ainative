#!/usr/bin/env python3
"""
extract_companion_app.py -- extract a course from a single-bundle companion app.

A third bundle shape, distinct from the two in extract_upgrade_path.py:

  * Not code-split. One `index-*.js` carries the whole course (~1.2 MB).
  * Served from scaledagile.com itself, not a replit host.
  * Quiz items use `stem` (not `question`) and each carries `lesson`, `lessonLabel`
    and `objectiveId`, so questions link to learning objectives directly.
  * The bundle also carries the full curriculum: lessons, shifts, objectives,
    sections and facilitator activities with slide refs and timings. The earlier
    apps exposed only a lesson manifest.

Minified binding names (`G0`, `$v`, `Xv`, …) change on every build, so nothing is
hardcoded: banks and curriculum arrays are found by their shape.

Usage:
    python3 tools/extract_companion_app.py chunks/index-D1iRUco4.js \\
        --source-id "src:2026-10-08/art-leader-trainer-enablement" \\
        --source-dir sources/art-leader-trainer-enablement/2026-10-08-bundle \\
        --course "course:scaledagile/art-leader-trainer-enablement" \\
        --title "AI-Native ART Leader Trainer Enablement" \\
        --knowledge-dir knowledge/courses/art-leader-trainer-enablement \\
        --url "https://art-leader-trainer-enablement.scaledagile.com/assets/index-D1iRUco4.js"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from js_object import JSParseError, parse_at  # noqa: E402

EXTRACTOR_VERSION = "0.1.0"
OPTION_KEYS = ("a", "b", "c", "d", "e", "f", "g", "h")

# matches `const X=[{`, `let X=[{`, and comma-chained `,X=[{`
BINDING = re.compile(r"[,;\s({]([A-Za-z_$][\w$]*)\s*=\s*(?=\[\{)")


def yaml_str(s) -> str:
    s = re.sub(r"\s+", " ", str(s)).strip()
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def slug(s: str, maxlen: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return s[:maxlen].rstrip("-")


def discover(text: str):
    """Find every array literal binding, classified by the shape of its first element."""
    banks, curricula = {}, {}
    for m in BINDING.finditer(text):
        name, pos = m.group(1), m.end()
        head = text[pos:pos + 500]
        is_bank = "stem:" in head and "options:" in head
        is_curr = "objectives:" in head and "sections:" in head
        if not (is_bank or is_curr):
            continue
        try:
            arr, _ = parse_at(text, pos)
        except (JSParseError, RecursionError, IndexError) as e:
            print(f"note: could not parse binding {name}: {e}", file=sys.stderr)
            continue
        if not isinstance(arr, list) or not arr:
            continue
        (banks if is_bank else curricula)[name] = arr
    return banks, curricula


def flatten_activities(lesson):
    """Yield (section, activity) pairs, including nested steps, in document order."""
    for sec in lesson.get("sections", []) or []:
        for act in sec.get("activities", []) or []:
            yield sec, act


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--source-dir", required=True)
    ap.add_argument("--course", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--knowledge-dir", required=True)
    ap.add_argument("--url", default="")
    ap.add_argument("--provider", default="provider:scaledagile")
    args = ap.parse_args()

    bundle = pathlib.Path(args.bundle)
    raw = bundle.read_bytes()
    text = raw.decode("utf-8", errors="replace")

    banks, curricula = discover(text)
    questions = [q for arr in banks.values() for q in arr]
    lessons = {}
    for arr in curricula.values():
        for les in arr:
            if isinstance(les.get("id"), int):
                lessons.setdefault(les["id"], les)

    if not questions:
        print("no quiz banks found in this bundle", file=sys.stderr)
        return 1
    print(f"{len(banks)} banks / {len(questions)} questions, {len(lessons)} lessons",
          file=sys.stderr)

    # integrity checks before anything is written
    problems = []
    for q in questions:
        if q.get("correctAnswer") not in (q.get("options") or []):
            problems.append(f"{q.get('id')}: correctAnswer is not one of the options")
        fb = q.get("optionFeedback") or {}
        missing = [o for o in (q.get("options") or []) if o not in fb]
        if missing:
            problems.append(f"{q.get('id')}: {len(missing)} option(s) without feedback")
    for p in problems:
        print(f"WARN {p}", file=sys.stderr)

    course_slug = args.course.rsplit("/", 1)[-1]
    sdir = pathlib.Path(args.source_dir)
    kdir = pathlib.Path(args.knowledge_dir)
    (sdir / "raw").mkdir(parents=True, exist_ok=True)
    (kdir / "quiz").mkdir(parents=True, exist_ok=True)
    (kdir / "lessons").mkdir(parents=True, exist_ok=True)

    # ---------- source layer ----------
    (sdir / "raw" / bundle.name).write_bytes(raw)
    (sdir / "raw" / "curriculum.json").write_text(
        json.dumps({"lessons": [lessons[i] for i in sorted(lessons)]},
                   indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    blocks, qblock = [], {}
    n = 0
    for q in questions:
        n += 1
        qblock[q["id"]] = f"b{n:04d}"
        blocks.append({"id": f"b{n:04d}", "type": "quiz_question",
                       "text": q.get("stem", ""), "frame": q.get("id", "")})
    objblock = {}
    for lid in sorted(lessons):
        for oi, otext in enumerate(lessons[lid].get("objectives", []) or [], 1):
            n += 1
            objblock[(lid, oi)] = f"b{n:04d}"
            blocks.append({"id": f"b{n:04d}", "type": "objective",
                           "text": otext, "frame": f"lesson-{lid}"})
    lesblock = {}
    for lid in sorted(lessons):
        n += 1
        lesblock[lid] = f"b{n:04d}"
        blocks.append({"id": f"b{n:04d}", "type": "lesson_title",
                       "text": lessons[lid].get("title", ""), "frame": f"lesson-{lid}"})
        for sec, act in flatten_activities(lessons[lid]):
            n += 1
            blocks.append({"id": f"b{n:04d}", "type": "activity",
                           "text": f"{act.get('id', '')} {act.get('title', '')}".strip(),
                           "frame": f"lesson-{lid}/{sec.get('id', '')}"})

    (sdir / "extracted.json").write_text(json.dumps({
        "source_id": args.source_id,
        "schema": "schemas/source.schema.json",
        "extractor": {"name": "extract_companion_app.py", "version": EXTRACTOR_VERSION},
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capture": {"original_filename": bundle.name, "url": args.url,
                    "saved_at_raw": None, "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest()},
        "frame_chain": [{"path": "bundle", "bytes": len(text)}],
        "bindings": {"banks": sorted(banks), "curriculum": sorted(curricula)},
        "integrity": {"problems": problems},
        "blocks": blocks,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ---------- course.yaml ----------
    lesson_id = {lid: f"lesson:{args.course.split(':', 1)[1]}/"
                      f"{lid:02d}-{slug(lessons[lid].get('title', ''))}"
                 for lid in sorted(lessons)}
    obj_id = {}
    out = ["# yaml-language-server: $schema=../../../schemas/course.schema.json",
           f'id: "{args.course}"', f"title: {yaml_str(args.title)}",
           f'provider: "{args.provider}"', "kind: certification-course",
           "language: en", f'url: {yaml_str(args.url)}', "delivery: spa", "", "objectives:"]
    for lid in sorted(lessons):
        for oi, otext in enumerate(lessons[lid].get("objectives", []) or [], 1):
            oid = f"obj:{course_slug}/l{lid}-o{oi}"
            obj_id[(lid, oi)] = oid
            out += [f'  - id: "{oid}"', f"    text: {yaml_str(otext)}",
                    f'    sources:\n      - "{args.source_id}#{objblock[(lid, oi)]}"']
    out += ["", "lessons:"]
    for lid in sorted(lessons):
        les = lessons[lid]
        out += [f'  - id: "{lesson_id[lid]}"', f"    order: {lid}",
                f"    title: {yaml_str(les.get('title', ''))}",
                "    capture_status: partial",
                f'    file: "lessons/{lid:02d}-{slug(les.get("title", ""))}.md"']
    out += ["", "sources:", f'  - "{args.source_id}#{lesblock[sorted(lessons)[0]]}"', ""]
    (kdir / "course.yaml").write_text("\n".join(out), encoding="utf-8")

    # ---------- lessons ----------
    # objective text -> id, so a question's objectiveId can resolve
    app_obj = {}
    for lid in sorted(lessons):
        for oi in range(1, len(lessons[lid].get("objectives", []) or []) + 1):
            app_obj[f"L{lid}-O{oi}"] = obj_id[(lid, oi)]

    for lid in sorted(lessons):
        les = lessons[lid]
        name = f"{lid:02d}-{slug(les.get('title', ''))}.md"
        fm = ["---", f'id: "{lesson_id[lid]}"', f'course: "{args.course}"',
              f"order: {lid}", f"title: {yaml_str(les.get('title', ''))}",
              "capture_status: partial", "objectives:"]
        fm += [f'  - "{obj_id[(lid, oi)]}"'
               for oi in range(1, len(les.get("objectives", []) or []) + 1)]
        fm += ["sources:", f'  - "{args.source_id}#{lesblock[lid]}"', "---", ""]

        body = [f"# {les.get('title', '')}", ""]
        if les.get("shift"):
            body += [f"**{les['shift']}**", ""]
        body += ["## Objectives", ""]
        body += [f"{oi}. {o}" for oi, o in enumerate(les.get("objectives", []) or [], 1)]
        body += ["", "## Structure", "",
                 "Facilitator outline as the companion app defines it. Activity prose and",
                 "slide content are not in the bundle, so this is structure, not teaching copy.",
                 ""]
        for sec in les.get("sections", []) or []:
            body += [f"### {sec.get('id', '')} {sec.get('title', '')}".strip(), ""]
            for act in sec.get("activities", []) or []:
                bits = [b for b in (act.get("slideRef"), act.get("timing"),
                                    act.get("format")) if b]
                meta = f" — {' · '.join(bits)}" if bits else ""
                body.append(f"- **{act.get('badge', 'Item')}** "
                            f"`{act.get('id', '')}` {act.get('title', '')}{meta}")
                for step in act.get("steps", []) or []:
                    sbits = [b for b in (step.get("timing"),) if b]
                    smeta = f" — {' · '.join(sbits)}" if sbits else ""
                    body.append(f"  - {step.get('title', '')}{smeta}")
            body.append("")
        (kdir / "lessons" / name).write_text("\n".join(fm + body) + "\n", encoding="utf-8")

    # ---------- quiz ----------
    for i, q in enumerate(questions, 1):
        opts = q.get("options") or []
        fb = q.get("optionFeedback") or {}
        correct = q.get("correctAnswer")
        lid = q.get("lesson")
        lines = [
            "# yaml-language-server: $schema=../../../../schemas/quiz-item.schema.json",
            f'id: "quiz:{args.course.split(":", 1)[1]}/lesson/{i:03d}"',
            f'course: "{args.course}"',
        ]
        if lid in lesson_id:
            lines.append(f'lesson: "{lesson_id[lid]}"')
        if q.get("objectiveId") in app_obj:
            lines.append(f'objective: "{app_obj[q["objectiveId"]]}"')
        lines += ["set: knowledge-check", "type: single-choice",
                  f"stem: {yaml_str(q.get('stem', ''))}", "options:"]
        for k, opt in zip(OPTION_KEYS, opts):
            lines += [f'  - key: "{k}"', f"    text: {yaml_str(opt)}",
                      f"    correct: {'true' if opt == correct else 'false'}"]
            if opt in fb:
                lines.append(f"    feedback: {yaml_str(fb[opt])}")
        lines += ["answer_status: confirmed",
                  f'sources:\n  - "{args.source_id}#{qblock[q["id"]]}"']
        (kdir / "quiz" / f"{i:03d}.yaml").write_text("\n".join(lines) + "\n",
                                                     encoding="utf-8")

    print(f"wrote {len(questions)} quiz items, {len(lessons)} lessons, "
          f"{len(obj_id)} objectives", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
