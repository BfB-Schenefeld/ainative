#!/usr/bin/env python3
"""
build_index.py -- derive query artifacts from the file-based knowledge base.

Writes (all gitignored, rebuild any time):
    index/knowledge.jsonl  one record per knowledge entity, flattened, with body text
    index/graph.json       nodes + typed edges, ready for a graph view
    index/coverage.md      what is captured vs. what is only known by name

The JSONL is the load format for anything downstream: RAG chunking, embeddings,
a spaced-repetition deck, or a migration into a real database.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "index"
FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


def split_md(path: pathlib.Path):
    m = FRONT_MATTER.match(path.read_text(encoding="utf-8"))
    if not m:
        return None, ""
    return yaml.safe_load(m.group(1)), m.group(2).strip()


def main() -> int:
    OUT.mkdir(exist_ok=True)
    records, nodes, edges = [], {}, []

    def node(nid: str, ntype: str, label: str, **extra) -> None:
        nodes[nid] = {"id": nid, "type": ntype, "label": label, **extra}

    def edge(src: str, rel: str, dst: str) -> None:
        edges.append({"from": src, "rel": rel, "to": dst})

    # sources
    for sfile in sorted((ROOT / "sources").rglob("source.yaml")):
        doc = yaml.safe_load(sfile.read_text(encoding="utf-8"))
        node(doc["source_id"], "source", doc["capture"]["url"], status=doc["coverage"]["status"])
        records.append({"id": doc["source_id"], "type": "source", "data": doc})

    # courses + objectives + lessons manifest
    for cfile in sorted((ROOT / "knowledge" / "courses").glob("*/course.yaml")):
        doc = yaml.safe_load(cfile.read_text(encoding="utf-8"))
        node(doc["id"], "course", doc["title"])
        records.append({"id": doc["id"], "type": "course", "data": doc})
        for s in doc.get("sources", []) or []:
            edge(doc["id"], "sourced_from", s.split("#")[0])
        for obj in doc.get("objectives", []) or []:
            node(obj["id"], "objective", obj["text"])
            edge(doc["id"], "has_objective", obj["id"])
            for c in obj.get("concepts", []) or []:
                edge(obj["id"], "about", c)
            records.append({"id": obj["id"], "type": "objective", "data": obj, "course": doc["id"]})
        for les in doc.get("lessons", []) or []:
            node(les["id"], "lesson", les["title"], capture_status=les["capture_status"])
            edge(doc["id"], "has_lesson", les["id"])
        for cert in doc.get("certifications", []) or []:
            edge(doc["id"], "upgrades", cert)

    # lesson bodies
    for lfile in sorted((ROOT / "knowledge" / "courses").glob("*/lessons/*.md")):
        fm, body = split_md(lfile)
        if not fm:
            continue
        node(fm["id"], "lesson", fm["title"], capture_status=fm["capture_status"])
        edge(fm["id"], "part_of", fm["course"])
        for c in fm.get("concepts", []) or []:
            edge(fm["id"], "mentions", c)
        for s in fm.get("sources", []) or []:
            edge(fm["id"], "sourced_from", s.split("#")[0])
        records.append({"id": fm["id"], "type": "lesson", "data": fm, "body": body})

    # quiz
    for qfile in sorted((ROOT / "knowledge" / "courses").glob("*/quiz/*.yaml")):
        doc = yaml.safe_load(qfile.read_text(encoding="utf-8"))
        node(doc["id"], "quiz_item", doc["stem"][:80], answer_status=doc["answer_status"])
        edge(doc["id"], "part_of", doc["course"])
        for c in doc.get("concepts", []) or []:
            edge(doc["id"], "tests", c)
        records.append({"id": doc["id"], "type": "quiz_item", "data": doc})

    # concepts
    for kfile in sorted((ROOT / "knowledge" / "concepts").glob("*.md")):
        fm, body = split_md(kfile)
        if not fm:
            continue
        node(fm["id"], "concept", fm["label"], status=fm["status"])
        for rel in ("broader", "narrower", "related", "part_of"):
            for r in fm.get(rel, []) or []:
                edge(fm["id"], rel, r)
        records.append({"id": fm["id"], "type": "concept", "data": fm, "body": body})

    # certifications
    for cfile in sorted((ROOT / "knowledge" / "certifications").glob("*.yaml")):
        doc = yaml.safe_load(cfile.read_text(encoding="utf-8"))
        node(doc["id"], "certification", doc["label"], tier=doc.get("tier"))
        for step in doc.get("upgrade_path", []) or []:
            edge(doc["id"], "requires" if step["required"] else "optional", step["course"])
        records.append({"id": doc["id"], "type": "certification", "data": doc})

    with (OUT / "knowledge.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (OUT / "graph.json").write_text(
        json.dumps({"nodes": list(nodes.values()), "edges": edges}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    lessons = [n for n in nodes.values() if n["type"] == "lesson"]
    concepts = [n for n in nodes.values() if n["type"] == "concept"]
    cap = sum(1 for l in lessons if l.get("capture_status") == "captured")
    defined = sum(1 for c in concepts if c.get("status") == "defined")
    lines = [
        "# Coverage (generated — do not edit)",
        "",
        f"- Lessons: **{cap} captured** / {len(lessons)} known",
        f"- Concepts: **{defined} defined** / {len(concepts)} minted",
        f"- Quiz items: **{sum(1 for n in nodes.values() if n['type'] == 'quiz_item')}**",
        "",
        "## Lessons known by name but not captured",
        "",
    ]
    lines += [f"- `{l['id']}` — {l['label']}" for l in lessons if l.get("capture_status") == "manifest_only"] or ["- none"]
    lines += ["", "## Concepts minted but not defined", ""]
    lines += [f"- `{c['id']}` — {c['label']}" for c in concepts if c.get("status") == "stub"] or ["- none"]
    (OUT / "coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{len(records)} records, {len(nodes)} nodes, {len(edges)} edges -> index/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
