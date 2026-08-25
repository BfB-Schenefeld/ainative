# Metamodel

Two layers, deliberately separated:

| Layer | Directory | Mutability | Purpose |
|---|---|---|---|
| **Source layer** | `sources/` | append-only, never hand-edited | What was captured, when, from where. Provenance and audit trail. |
| **Knowledge layer** | `knowledge/` | curated, hand- or tool-edited | What we actually know. Deduplicated, normalized, linkable. |

Every knowledge record carries `sources: [...]` pointing back at source-layer block
IDs. Nothing in `knowledge/` is allowed to exist without at least one source
reference. That constraint is enforced by `tools/validate.py`.

```
Capture (HTML export)
   │  tools/extract_singlefile.py
   ▼
Source ──< Block                  (source layer, verbatim + provenance)
   │
   │  curation (manual or LLM-assisted)
   ▼
Course ──< Lesson ──< Objective   (knowledge layer)
   │          │
   │          └──< QuizItem ──> Concept
   │
   └──> Certification
```

## Entities

### Source
One capture event = one directory under `sources/<provider>/<date>-<slug>/`.

| Field | Notes |
|---|---|
| `source_id` | `src:YYYY-MM-DD/<slug>` |
| `capture.url` | original URL, read from the SingleFile header |
| `capture.sha256` | hash of the *original* file, before stripping |
| `frame_chain` | the nested-iframe path the extractor walked |
| `blocks[]` | ordered content blocks, `b0001`… stable within the source |

Blocks are the citation unit. A knowledge record cites
`src:2026-08-25/learning-plans-exams#b0033`.

### Course
A learning unit as the provider packages it. Holds the lesson manifest (including
lessons not yet captured, so gaps are visible), objectives, and certification links.

### Lesson
Markdown + YAML front matter. Prose lives in the Markdown body because that is what
humans and LLMs both read well; everything queryable lives in front matter.
`capture_status: captured | manifest_only | partial` makes coverage explicit.

### QuizItem
Structured, never prose: `stem`, `options[]` with `correct: true|false`, `rationale`,
`concepts[]`. This is the format an exam-prep tool or spaced-repetition deck consumes
directly.

### Concept
The graph node. A term, principle, or practice ("Outcome-Driven Flow"). Concepts are
what let knowledge from *different* courses and captures join up — which is the whole
point of doing this across many exports rather than keeping N separate documents.
Relations: `broader`, `narrower`, `related`, `part_of`.

### Certification
Credential and its upgrade path. Ties courses to an outcome.

## Why files and not a database

- Diffs are readable, so curation is reviewable in PRs.
- Git gives free versioning of an evolving knowledge base.
- LLMs consume Markdown + YAML natively; no export step.
- `tools/build_index.py` derives `index/knowledge.jsonl` + `index/graph.json` on
  demand, so a query layer is one build away. The derived index is not committed.

## Open decisions

- Whether `sources/` gets split into a separate private repo once the corpus grows
  (see `docs/adr/0002-capture-strategy.md`).
- Embeddings: out of scope for the POC. Index format is already JSONL so vectors can
  be bolted on per record.
