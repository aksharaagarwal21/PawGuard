# ADR 0008 — Assisted identification: gate, preview, search and decisions

Date: 2026-10-06 · Status: accepted

## Context

Phase 7 needs the full integration (model registry, gallery embeddings, search, candidate UI, human decisions,
feedback, rollback) and an honest evaluation. The only identity data available is DogFaceNet — aligned face crops
of pet dogs with unreviewed labels — which cannot show whether matching works for community dogs photographed in
the field. The release gate in `ML_PLAN.md` therefore cannot be met yet.

## Decisions

1. **The release gate is enforced by the database.** `model_versions.release_gate` is recorded from the model
   manifest; a check constraint makes `state = 'active'` impossible for an identity model unless
   `release_gate.passed` is true. The CLI also refuses activation while the gallery index for the new model is
   incomplete (< 90% of eligible photos embedded).
2. **Research preview only in demo organisations.** A *staged* model may be flagged `research_preview`. The API
   offers it only to organisations with `is_demo = true`, labels every response `mode = research_preview`, and the
   UI shows a "Research preview — not validated" notice. Real organisations see "unavailable" with the reason
   `research_only` and keep the manual workflow.
3. **Exact cosine search per organisation and model version.** pgvector with no approximate index (brief §5);
   aggregation (the validated rule, currently the identity centroid) runs in SQL — cosine distance ignores vector
   length, so `avg(embedding)` is the centroid. Vectors of different model versions are never compared. Only the
   worker reads or writes vectors; the API never returns them.
4. **Candidates, not scores.** Search returns at most `candidate_list_size` animals whose aggregated similarity
   reaches the threshold chosen on validation, each with its two most similar photos. Scores are stored for
   evaluation but never returned by the API or shown: cosine similarity is not a probability.
5. **Decisions are explicit and separate from linking.** `identity_decisions` (append-only: same animal / new /
   not sure, with the candidate rank or "not suggested") is the correction-feedback record. Linking happens only
   when the person confirms and the sighting is created through the normal observation command.
6. **Index lifecycle.** `index_wanted` keeps embeddings current for a model (enrolment jobs when a linked,
   chosen-subject photo is approved). `models reindex` builds a new collection before switching; the previous
   model's embeddings stay, so rollback is re-activating the previous version. Searches report `stale_index`
   when the index is incomplete instead of silently missing animals.
7. **Gallery eligibility.** Only photos where a person chose the subject box (detector-proposed) and the sighting
   is linked to a non-archived animal are enrolled. Merged aliases count toward their canonical animal.

## Consequences

- Real organisations get no suggestions until a model passes the gate on permissioned field data.
- The demo shows the complete workflow with a clearly labelled research model.
- Photos where the detector found no dog cannot be enrolled or searched by subject (no manual box drawing yet).
