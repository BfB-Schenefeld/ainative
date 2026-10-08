#!/usr/bin/env python3
"""
export_quiz.py -- export quiz records to a human-readable workbook and CSV.

Reads knowledge/courses/<slug>/quiz/*.yaml and writes:
  <out>.xlsx   three sheets: Questions (wide), Answer options (long), Info
  <out>.csv    semicolon-delimited, UTF-8 BOM, so German Excel opens it directly

Labels are English. The semicolon delimiter is a regional Excel convention, not a
language choice, so it stays.

Usage:
    python3 tools/export_quiz.py --course ai-native-safe-overview --out exports/final-quiz
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import sys

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = pathlib.Path(__file__).resolve().parent.parent

HEAD_FILL = PatternFill("solid", fgColor="1F3864")
HEAD_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
BASE_FONT = Font(name="Arial", size=10)
BOLD = Font(name="Arial", size=10, bold=True)
OK_FILL = PatternFill("solid", fgColor="D9EAD3")
NO_FILL = PatternFill("solid", fgColor="FCE8E6")
ALT_FILL = PatternFill("solid", fgColor="F2F2F2")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
TOPWRAP = Alignment(wrap_text=True, vertical="top")

TYPE_LABEL = {"single-choice": "Single choice", "multiple-choice": "Multiple choice",
              "true-false": "True / false", "matching": "Matching", "open": "Open"}
SET_LABEL = {"final": "Final quiz", "knowledge-check": "Knowledge check",
             "practice": "Practice", "unknown": "Unknown"}


def load(course: str):
    qdir = ROOT / "knowledge" / "courses" / course / "quiz"
    items = []
    for f in sorted(qdir.glob("*.yaml")):
        items.append(yaml.safe_load(f.read_text(encoding="utf-8")))
    return items


def load_course(course: str) -> dict:
    cfile = ROOT / "knowledge" / "courses" / course / "course.yaml"
    try:
        return yaml.safe_load(cfile.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def load_lesson_titles(doc: dict) -> dict:
    """Real lesson titles from course.yaml, so the export shows names not slugs."""
    return {les["id"]: les["title"] for les in doc.get("lessons", []) or []}


LESSON_TITLES: dict = {}


def lesson_label(item) -> str:
    ref = item.get("lesson") or ""
    if ref in LESSON_TITLES:
        return LESSON_TITLES[ref]
    tail = ref.rsplit("/", 1)[-1] if ref else ""
    return tail.replace("-", " ").strip() if tail else "unknown"


def wide_rows(items, maxopt, has_diff, has_rat):
    """One row per question: every option, its verdict, and its explanation."""
    header = ["No", "ID", "Type"] + (["Difficulty"] if has_diff else []) + ["Lesson", "Question"]
    for i in range(maxopt):
        L = chr(65 + i)
        header += [f"Option {L}", f"{L} correct?", f"Feedback {L}"]
    header += ["Correct answer", "Feedback (correct)"]
    header += (["Question rationale"] if has_rat else []) + ["Answer status", "Source"]

    rows = []
    for n, it in enumerate(items, 1):
        opts = it.get("options", []) or []
        correct = next((o for o in opts if o.get("correct")), None)
        row = [
            n,
            it.get("id", ""),
            TYPE_LABEL.get(it.get("type", ""), it.get("type", "")),
        ]
        if has_diff:
            row.append(it.get("difficulty", ""))
        row += [lesson_label(it), it.get("stem", "")]
        for i in range(maxopt):
            if i < len(opts):
                o = opts[i]
                row += [o.get("text", ""),
                        "CORRECT" if o.get("correct") else "wrong",
                        o.get("feedback", "")]
            else:
                row += ["", "", ""]
        row += [correct.get("text", "") if correct else "",
                correct.get("feedback", "") if correct else ""]
        if has_rat:
            row.append(it.get("rationale", ""))
        row += [it.get("answer_status", ""), (it.get("sources") or [""])[0]]
        rows.append(row)
    return header, rows


def long_rows(items, has_diff, has_rat):
    """One row per option: easier to filter, sort and pivot."""
    header = ["No", "Question ID"] + (["Difficulty"] if has_diff else [])
    header += ["Lesson", "Question", "Option", "Answer text", "Correct?", "Feedback"]
    header += ["Question rationale"] if has_rat else []
    rows = []
    for n, it in enumerate(items, 1):
        for o in it.get("options", []) or []:
            row = [n, it.get("id", "")]
            if has_diff:
                row.append(it.get("difficulty", ""))
            row += [lesson_label(it), it.get("stem", ""), (o.get("key") or "").upper(),
                    o.get("text", ""),
                    "CORRECT" if o.get("correct") else "wrong", o.get("feedback", "")]
            if has_rat:
                row.append(it.get("rationale", "") if o.get("correct") else "")
            rows.append(row)
    return header, rows


def style_sheet(ws, header, rows, widths, wrap_cols, verdict_cols, row_height=None):
    ws.append(header)
    for r in rows:
        ws.append(r)
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    for cell in ws[1]:
        cell.font = HEAD_FONT
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = BOX
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(header))}{len(rows) + 1}"
    for ri, row in enumerate(ws.iter_rows(min_row=2), start=2):
        for cell in row:
            cell.font = BASE_FONT
            cell.border = BOX
            if cell.column in wrap_cols:
                cell.alignment = TOPWRAP
            else:
                cell.alignment = Alignment(vertical="top")
            if cell.column in verdict_cols:
                cell.alignment = Alignment(vertical="top", horizontal="center")
                if cell.value == "CORRECT":
                    cell.fill = OK_FILL
                    cell.font = BOLD
                elif cell.value == "wrong":
                    cell.fill = NO_FILL
            elif ri % 2 == 0 and cell.column not in verdict_cols:
                cell.fill = ALT_FILL
        if row_height:
            ws.row_dimensions[ri].height = row_height


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--course", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    global LESSON_TITLES
    items = load(args.course)
    if not items:
        print("no quiz items found", file=sys.stderr)
        return 1
    course_doc = load_course(args.course)
    LESSON_TITLES = load_lesson_titles(course_doc)
    # only emit as many option columns as the bank actually uses
    maxopt = max((len(it.get("options") or []) for it in items), default=0)
    # a column that is empty for every item in this bank is noise, so leave it out
    has_diff = any(it.get("difficulty") for it in items)
    has_rat = any(it.get("rationale") for it in items)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    wh, wr = wide_rows(items, maxopt, has_diff, has_rat)
    lh, lr = long_rows(items, has_diff, has_rat)

    wb = Workbook()
    ws = wb.active
    ws.title = "Questions"
    FIRST = 6 + (1 if has_diff else 0)  # first option column
    wide_widths = [5, 40, 15] + ([14] if has_diff else []) + [40, 60]
    for _ in range(maxopt):
        wide_widths += [50, 12, 62]
    wide_widths += [50, 62] + ([66] if has_rat else []) + [14, 42]
    last = FIRST + maxopt * 3
    wide_wrap = ({FIRST - 2, FIRST - 1} | {c for c in range(FIRST, last) if (c - FIRST) % 3 != 1}
                 | set(range(last, last + 2 + (1 if has_rat else 0))))
    wide_verdict = {c for c in range(FIRST, last) if (c - FIRST) % 3 == 1}
    style_sheet(ws, wh, wr, wide_widths, wide_wrap, wide_verdict, row_height=110)

    ws2 = wb.create_sheet("Answer options")
    d = 1 if has_diff else 0
    long_widths = [5, 40] + ([14] if has_diff else []) + [40, 60, 8, 55, 12, 70]
    long_widths += [66] if has_rat else []
    style_sheet(ws2, lh, lr, long_widths,
                {3 + d, 4 + d, 6 + d, 8 + d, 9 + d}, {5 + d, 7 + d}, row_height=58)

    info = wb.create_sheet("Info")
    bands, sets, lessons_seen, sources = {}, {}, {}, []
    for it in items:
        if it.get("difficulty"):
            bands[it["difficulty"]] = bands.get(it["difficulty"], 0) + 1
        st = it.get("set", "unknown")
        sets[st] = sets.get(st, 0) + 1
        lab = lesson_label(it)
        lessons_seen[lab] = lessons_seen.get(lab, 0) + 1
        for src in it.get("sources") or []:
            base = src.split("#")[0]
            if base not in sources:
                sources.append(base)

    def dist(d, order=None):
        keys = sorted(d, key=lambda k: order.index(k) if order and k in order else 99)
        return ", ".join(f"{k}: {d[k]}" for k in keys)

    rows = [
        [course_doc.get("title") or args.course, ""],
        ["", ""],
        ["Questions in pool", len(items)],
        ["Answer options per question", maxopt],
        ["Question sets", dist(sets, ["final", "knowledge-check", "practice", "unknown"])],
    ]
    if bands:
        rows.append(["Difficulty split", dist(bands, ["easy", "medium", "harder"])])
    if len(lessons_seen) > 1:
        rows.append(["Questions per lesson",
                     "; ".join(f"{k} ({v})" for k, v in lessons_seen.items())])
    confirmed = sum(1 for it in items if it.get("answer_status") == "confirmed")
    rows += [
        ["Confirmed answer keys", f"{confirmed} of {len(items)}"],
        ["", ""],
        ["Sheet \u201cQuestions\u201d", "One row per question, all options side by side."],
        ["Sheet \u201cAnswer options\u201d",
         "One row per answer option, for filtering, sorting and pivoting."],
        ["", ""],
        ["Source", ", ".join(sources) or "unknown"],
        ["Rights", "Scaled Agile, Inc. Not for redistribution "
                   "(rights.redistribution: none in every source record)."],
        ["Generated", "tools/export_quiz.py from the records in knowledge/courses/"
                      f"{args.course}/quiz/. Regenerate rather than editing this file."],
    ]
    for r in rows:
        info.append(r)
    info.column_dimensions["A"].width = 28
    info.column_dimensions["B"].width = 95
    for row in info.iter_rows():
        for cell in row:
            cell.font = BASE_FONT
            cell.alignment = TOPWRAP
    info["A1"].font = Font(name="Arial", size=13, bold=True)
    for ri in range(3, len(rows) + 1):
        if info[f"A{ri}"].value:
            info[f"A{ri}"].font = BOLD

    xlsx = out.with_suffix(".xlsx")
    wb.save(xlsx)

    csv_path = out.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        w.writerow(wh)
        for r in wr:
            w.writerow([str(c).replace("\r\n", " ").replace("\n", " ") if c is not None else "" for c in r])

    csv_long = out.parent / (out.name + "-options.csv")
    with csv_long.with_suffix(".csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        w.writerow(lh)
        for r in lr:
            w.writerow([str(c).replace("\n", " ") if c is not None else "" for c in r])

    print(f"{len(items)} questions, {len(lr)} options -> {xlsx.name}, {csv_path.name}, "
          f"{csv_long.with_suffix('.csv').name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
