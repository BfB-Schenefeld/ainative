# ID scheme

All IDs are `type:path` URNs. Lowercase, ASCII, `-` as word separator. IDs are
permanent — if content changes meaning, mint a new ID and mark the old one
`superseded_by`.

| Type | Pattern | Example |
|---|---|---|
| Source | `src:YYYY-MM-DD/<slug>` | `src:2026-08-25/learning-plans-exams` |
| Block | `<source_id>#<block_id>` | `src:2026-08-25/learning-plans-exams#b0033` |
| Provider | `provider:<slug>` | `provider:scaledagile` |
| Course | `course:<provider>/<slug>` | `course:scaledagile/ai-native-safe-overview` |
| Lesson | `lesson:<provider>/<course>/<nn>-<slug>` | `lesson:scaledagile/ai-native-safe-overview/00-welcome` |
| Objective | `obj:<course-slug>/<nn>` | `obj:ai-native-safe-overview/01` |
| Quiz item | `quiz:<provider>/<course>/<set>/<nnn>` | `quiz:scaledagile/ai-native-safe-overview/final/001` |
| Concept | `concept:<slug>` | `concept:outcome-driven-flow` |
| Certification | `cert:<provider>/<slug>` | `cert:scaledagile/spc` |

Concept IDs are intentionally **not** namespaced by provider. A concept is supposed
to be the join point across sources. If two providers mean genuinely different things
by the same word, disambiguate in the slug (`concept:flow-safe` vs `concept:flow-tps`),
not by namespacing everything by default.

File paths mirror IDs so that an ID is greppable:
`course:scaledagile/ai-native-safe-overview` → `knowledge/courses/ai-native-safe-overview/course.yaml`.
