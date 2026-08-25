#!/usr/bin/env python3
"""
validate.py -- schema validation + referential integrity for the knowledge base.

Checks:
  1. Every YAML/front-matter record validates against its JSON Schema.
  2. Every declared ID matches the pattern for its type and matches its file path.
  3. Every `sources:` reference resolves to a real source and a real block ID.
  4. Every concept / course / lesson / certification cross-reference resolves.
  5. No record exists without at least one source reference.

Exit code 0 = clean, 1 = errors found.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml jsonschema")
try:
    from jsonschema import Draft202012Validator
except ImportError:
    sys.exit("pip install pyyaml jsonschema")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"

ERRORS: list[str] = []
WARNINGS: list[str] = []


def err(msg: str) -> None:
    ERRORS.append(msg)


def warn(msg: str) -> None:
    WARNINGS.append(msg)


def load_schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMAS / name).read_text(encoding="utf-8")))


FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)


def read_front_matter(path: pathlib.Path):
    text = path.read_text(encoding="utf-8")
    m = FRONT_MATTER.match(text)
    if not m:
        err(f"{path.relative_to(ROOT)}: missing YAML front matter")
        return None
    return yaml.safe_load(m.group(1))


def check(schema: Draft202012Validator, doc, path: pathlib.Path) -> None:
    for e in sorted(schema.iter_errors(doc), key=lambda x: list(x.path)):
        loc = "/".join(str(p) for p in e.path) or "<root>"
        err(f"{path.relative_to(ROOT)}: {loc}: {e.message}")


def main() -> int:
    # ---------- sources ----------
    source_schema = load_schema("source.schema.json")
    known_blocks: set[str] = set()
    known_sources: set[str] = set()

    for sfile in sorted((ROOT / "sources").rglob("source.yaml")):
        doc = yaml.safe_load(sfile.read_text(encoding="utf-8"))
        check(source_schema, doc, sfile)
        sid = doc.get("source_id")
        known_sources.add(sid)
        extracted = sfile.parent / "extracted.json"
        if not extracted.exists():
            warn(f"{sfile.relative_to(ROOT)}: no extracted.json alongside source.yaml")
            continue
        ex = json.loads(extracted.read_text(encoding="utf-8"))
        if ex.get("source_id") != sid:
            err(f"{extracted.relative_to(ROOT)}: source_id mismatch with source.yaml")
        for b in ex.get("blocks", []):
            known_blocks.add(f"{sid}#{b['id']}")

    # ---------- knowledge ----------
    course_schema = load_schema("course.schema.json")
    lesson_schema = load_schema("lesson.schema.json")
    quiz_schema = load_schema("quiz-item.schema.json")
    concept_schema = load_schema("concept.schema.json")
    cert_schema = load_schema("certification.schema.json")

    known_ids: set[str] = set()
    refs: list[tuple[str, str, pathlib.Path]] = []  # (kind, id, file)

    def collect_sources(doc, path: pathlib.Path) -> None:
        for ref in doc.get("sources", []) or []:
            if "#" in ref:
                if ref not in known_blocks:
                    err(f"{path.relative_to(ROOT)}: dangling source block {ref}")
            elif ref not in known_sources:
                err(f"{path.relative_to(ROOT)}: unknown source {ref}")

    for cfile in sorted((ROOT / "knowledge" / "courses").glob("*/course.yaml")):
        doc = yaml.safe_load(cfile.read_text(encoding="utf-8"))
        check(course_schema, doc, cfile)
        known_ids.add(doc["id"])
        slug = doc["id"].split("/")[-1]
        if cfile.parent.name != slug:
            err(f"{cfile.relative_to(ROOT)}: directory '{cfile.parent.name}' != id slug '{slug}'")
        collect_sources(doc, cfile)
        for obj in doc.get("objectives", []) or []:
            known_ids.add(obj["id"])
            collect_sources(obj, cfile)
            for c in obj.get("concepts", []) or []:
                refs.append(("concept", c, cfile))
        for les in doc.get("lessons", []) or []:
            known_ids.add(les["id"])
            f = les.get("file")
            if les["capture_status"] != "manifest_only" and not f:
                err(f"{cfile.relative_to(ROOT)}: lesson {les['id']} is {les['capture_status']} but has no file")
            if f and not (cfile.parent / f).exists():
                err(f"{cfile.relative_to(ROOT)}: lesson file {f} not found")
        for cert in doc.get("certifications", []) or []:
            refs.append(("cert", cert, cfile))

    for lfile in sorted((ROOT / "knowledge" / "courses").glob("*/lessons/*.md")):
        doc = read_front_matter(lfile)
        if doc is None:
            continue
        check(lesson_schema, doc, lfile)
        known_ids.add(doc["id"])
        collect_sources(doc, lfile)
        refs.append(("course", doc["course"], lfile))
        for c in doc.get("concepts", []) or []:
            refs.append(("concept", c, lfile))
        for o in doc.get("objectives", []) or []:
            refs.append(("objective", o, lfile))

    for qfile in sorted((ROOT / "knowledge" / "courses").glob("*/quiz/*.yaml")):
        doc = yaml.safe_load(qfile.read_text(encoding="utf-8"))
        check(quiz_schema, doc, qfile)
        known_ids.add(doc["id"])
        collect_sources(doc, qfile)
        refs.append(("course", doc["course"], qfile))
        opts = doc.get("options") or []
        correct = [o for o in opts if o.get("correct")]
        if doc.get("answer_status") == "confirmed" and not correct:
            err(f"{qfile.relative_to(ROOT)}: answer_status=confirmed but no option marked correct")
        if doc.get("answer_status") == "unknown" and correct:
            err(f"{qfile.relative_to(ROOT)}: answer_status=unknown but an option is marked correct")
        if doc.get("type") == "single-choice" and len(correct) > 1:
            err(f"{qfile.relative_to(ROOT)}: single-choice with {len(correct)} correct options")
        for c in doc.get("concepts", []) or []:
            refs.append(("concept", c, qfile))

    for kfile in sorted((ROOT / "knowledge" / "concepts").glob("*.md")):
        doc = read_front_matter(kfile)
        if doc is None:
            continue
        check(concept_schema, doc, kfile)
        known_ids.add(doc["id"])
        if doc["id"] != f"concept:{kfile.stem}":
            err(f"{kfile.relative_to(ROOT)}: id does not match filename")
        collect_sources(doc, kfile)
        for rel in ("broader", "narrower", "related", "part_of"):
            for r in doc.get(rel, []) or []:
                refs.append(("concept", r, kfile))

    for cfile in sorted((ROOT / "knowledge" / "certifications").glob("*.yaml")):
        doc = yaml.safe_load(cfile.read_text(encoding="utf-8"))
        check(cert_schema, doc, cfile)
        known_ids.add(doc["id"])
        collect_sources(doc, cfile)
        for step in doc.get("upgrade_path", []) or []:
            refs.append(("course?", step["course"], cfile))

    # ---------- cross-references ----------
    for kind, ref, path in refs:
        if ref in known_ids:
            continue
        if kind.endswith("?"):
            warn(f"{path.relative_to(ROOT)}: forward reference to not-yet-captured {ref}")
        else:
            err(f"{path.relative_to(ROOT)}: dangling {kind} reference {ref}")

    # ---------- report ----------
    for w in WARNINGS:
        print(f"WARN  {w}")
    for e in ERRORS:
        print(f"ERROR {e}")
    print(
        f"\n{len(known_sources)} sources, {len(known_blocks)} blocks, {len(known_ids)} knowledge IDs, "
        f"{len(ERRORS)} errors, {len(WARNINGS)} warnings"
    )
    return 1 if ERRORS else 0


if __name__ == "__main__":
    raise SystemExit(main())
