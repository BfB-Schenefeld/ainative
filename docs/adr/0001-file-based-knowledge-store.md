# ADR 0001 — File-based knowledge store in Git

**Status:** accepted · 2026-08-25

## Context
A growing corpus of learning content captured from web exports needs a home. Options
considered: a database (Postgres/SQLite), a wiki, a vector store, or plain files in Git.

## Decision
Plain files in Git. Markdown + YAML front matter for prose-bearing records, YAML for
purely structured records, JSON Schema for validation, derived indexes built on demand
and never committed.

## Rationale
- Curation is the expensive part, and curation needs review. PR diffs give that for free.
- The corpus is small (thousands of records, not millions). A database buys nothing yet.
- Markdown + YAML is the native input format for the LLM tooling this corpus exists to feed.
- A vector index is derivable from files; files are not derivable from a vector index.

## Consequences
- No transactions, no concurrent-write safety. Acceptable for a single curator.
- Referential integrity must be enforced by a linter (`tools/validate.py`), not by the store.
- If the corpus outgrows this, `index/knowledge.jsonl` is already the load format for
  whatever comes next.
