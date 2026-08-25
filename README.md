# ainative — a knowledge base built from captured learning content

A file-based, version-controlled knowledge store for AI-Native SAFe learning material.
Web exports go in one end as provenance; a curated, cross-linked knowledge graph comes
out the other.

**Status:** proof of concept. One capture ingested, pipeline validated end to end.

## Layout

```
sources/          append-only captures + provenance (never hand-edited)
knowledge/        curated records: courses, lessons, quiz items, concepts, certifications
schemas/          JSON Schema for every record type
tools/            extractor, validator, index builder
docs/             metamodel, ID scheme, ingestion runbook, ADRs
index/            derived — gitignored, rebuild with tools/build_index.py
```

Read `docs/metamodel.md` first, then `docs/ingestion.md`. For capturing Rise 360
courses with their quiz answer keys intact, `docs/capture-rise.md`.

## Quick start

```bash
pip install pyyaml jsonschema beautifulsoup4 lxml

# ingest a capture
python3 tools/extract_singlefile.py capture.html \
    --out sources/scaledagile-community/2026-09-01-some-page \
    --source-id "src:2026-09-01/some-page"

# curate by hand into knowledge/, then
python3 tools/validate.py      # schema + referential integrity
python3 tools/build_index.py   # index/knowledge.jsonl, graph.json, coverage.md
```

## What is in here so far

From `src:2026-08-25/learning-plans-exams`:

- 1 course — *AI-Native SAFe Overview*, 9-entry lesson manifest, 4 learning objectives
- 1 lesson captured in full (Welcome); 8 known by name only
- 11 concepts (2 defined, 9 stubs)
- 3 certifications with their upgrade paths
- 0 quiz items

`index/coverage.md` shows the gaps after every build.

## Read this before adding more captures

That first export was 8.5 MB and yielded one lesson. **Full-page HTML exports are the
wrong capture method for these courses.**

The upgrade path turned out to be a public Vite/React SPA, not a Rise 360 course — its
bundle chunks are static files containing the full quiz bank with answer keys. See
`docs/capture-upgrade-path.md` for the procedure and `docs/adr/0003-not-a-rise-course.md`
for how that was found. `docs/capture-rise.md` still applies to actual Rise courses. Fixing the capture step is worth more than any amount of work on
this repo.

## Rights

Captured material is Scaled Agile, Inc. training content, held under personal learner
access. `redistribution: none` in every source record. See `NOTICE.md`.
