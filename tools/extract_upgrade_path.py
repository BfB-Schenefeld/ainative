#!/usr/bin/env python3
"""
extract_upgrade_path.py -- turn a bundle chunk from the AI-Native SAFe upgrade-path app
into source-layer JSON plus knowledge-layer quiz records.

The upgrade path is not a Rise 360 course. It is a Vite/React single-page app served
from a public static host, code-split into per-lesson chunks under /assets/. The chunk
`FinalQuiz-*.js` holds the full question bank: stems, options, the correct answer, and
per-option feedback for correct *and* incorrect choices.

Usage:
    # 1. save the chunk locally (see docs/capture-upgrade-path.md)
    # 2. extract
    python3 tools/extract_upgrade_path.py FinalQuiz-DUvUYCnK.js \
        --source-id "src:2026-08-26/upgrade-path-final-quiz" \
        --source-dir sources/ai-native-upgrade-path/2026-08-26-final-quiz \
        --quiz-dir knowledge/courses/ai-native-safe-overview/quiz \
        --course "course:scaledagile/ai-native-safe-overview"
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
from js_object import JSParseError, find_binding  # noqa: E402

EXTRACTOR_VERSION = "0.1.0"
KEYS = ("a", "b", "c", "d", "e", "f", "g", "h")


def yaml_str(s: str, indent: int) -> str:
    """Emit a YAML double-quoted scalar, folded onto one line."""
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def load_lesson_ids(course_file):
    """order -> lesson id, so 'Lesson 3' resolves to a real ID the validator can check."""
    if not course_file:
        return {}
    try:
        import yaml
        doc = yaml.safe_load(pathlib.Path(course_file).read_text(encoding="utf-8"))
        return {les["order"]: les["id"] for les in doc.get("lessons", []) or []}
    except Exception:
        return {}


def resolve_lesson(label: str, by_order: dict):
    m = re.search(r"Lesson\s*(\d+)", label or "")
    if not m:
        return None
    return by_order.get(int(m.group(1)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("chunk")
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--source-dir", required=True)
    ap.add_argument("--quiz-dir", required=True)
    ap.add_argument("--course", required=True)
    ap.add_argument("--set", default="final")
    ap.add_argument("--url", default="")
    ap.add_argument("--course-file", default=None,
                    help="course.yaml used to resolve 'Lesson N' labels to real lesson IDs")
    args = ap.parse_args()

    chunk = pathlib.Path(args.chunk)
    raw = chunk.read_bytes()
    text = raw.decode("utf-8", errors="replace")

    preparsed = json.loads(text) if chunk.suffix == ".json" else None

    if preparsed is not None:
        bank = preparsed["QUESTION_BANK"]
        meta = {k: preparsed[k] for k in ("QUIZ_SIZE", "PASSING_SCORE") if k in preparsed}
        lesson_map = preparsed.get("SOURCE_LESSONS", {})
    else:
        try:
            bank = find_binding(text, "QUESTION_BANK")
        except JSParseError as e:
            print(f"Could not locate QUESTION_BANK: {e}", file=sys.stderr)
            print("Check you saved the FinalQuiz-*.js chunk, not index-*.js.", file=sys.stderr)
            return 1
        meta = {}
        for name in ("QUIZ_SIZE", "PASSING_SCORE"):
            try:
                meta[name] = find_binding(text, name)
            except JSParseError:
                pass
        # source-lesson map is usually an unexported local; find it by shape
        lesson_map = {}
        m = re.search(r'\{"(?:final-)?q?\w+-?q?\d+"\s*:\s*"Lesson', text)
        if m:
            try:
                from js_object import parse_at
                lesson_map = parse_at(text, m.start())[0]
            except JSParseError:
                pass

    # ---- source layer ----
    sdir = pathlib.Path(args.source_dir)
    (sdir / "raw").mkdir(parents=True, exist_ok=True)
    (sdir / "raw" / chunk.name).write_bytes(raw)

    blocks = []
    for n, q in enumerate(bank, 1):
        blocks.append({
            "id": f"b{n:04d}",
            "type": "quiz_question",
            "text": q.get("question", ""),
            "frame": q.get("id", ""),
        })
    (sdir / "extracted.json").write_text(json.dumps({
        "source_id": args.source_id,
        "schema": "schemas/source.schema.json",
        "extractor": {"name": "extract_upgrade_path.py", "version": EXTRACTOR_VERSION},
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capture": {
            "original_filename": chunk.name,
            "url": args.url,
            "saved_at_raw": None,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        "frame_chain": [{"path": "bundle-chunk", "bytes": len(text)}],
        "quiz_meta": meta,
        "blocks": blocks,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ---- knowledge layer ----
    lesson_ids = load_lesson_ids(args.course_file)
    qdir = pathlib.Path(args.quiz_dir)
    qdir.mkdir(parents=True, exist_ok=True)
    written = 0
    for n, q in enumerate(bank, 1):
        opts = q.get("options", []) or []
        correct = q.get("correctAnswer")
        fb = q.get("optionFeedback", {}) or {}
        multi = isinstance(correct, list)
        correct_set = set(correct) if multi else {correct}

        lines = [
            "# yaml-language-server: $schema=../../../../schemas/quiz-item.schema.json",
            f'id: "quiz:{args.course.split(":", 1)[1]}/{args.set}/{n:03d}"',
            f'course: "{args.course}"',
            f"set: {args.set}",
            f"type: {'multiple-choice' if multi else 'single-choice'}",
            f"stem: {yaml_str(q.get('question', ''), 0)}",
            "options:",
        ]
        for k, opt in zip(KEYS, opts):
            lines.append(f'  - key: "{k}"')
            lines.append(f"    text: {yaml_str(opt, 4)}")
            lines.append(f"    correct: {'true' if opt in correct_set else 'false'}")
            if opt in fb:
                lines.append(f"    feedback: {yaml_str(fb[opt], 4)}")
        lines.append("answer_status: confirmed")
        src_lesson = resolve_lesson(lesson_map.get(q.get("id", "")), lesson_ids)
        if src_lesson:
            lines.append(f'lesson: "{src_lesson}"')
        lines.append(f'sources:\n  - "{args.source_id}#b{n:04d}"')
        (qdir / f"{n:03d}.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1

    print(f"{written} quiz items -> {qdir}", file=sys.stderr)
    print(f"quiz meta: {meta}", file=sys.stderr)
    if not lesson_map:
        print("note: source-lesson map not found; items written without lesson links", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
