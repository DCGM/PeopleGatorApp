# people-gator-api

Backend service for People Gator.

This repository keeps specification content in focused documents to avoid contradictions between product goals, architecture choices, and API contracts:

1. Product specification: `docs/01-product-spec.md`
2. Entity relations: `docs/02-entity-relations.md`
3. Architecture specification: `docs/03-architecture-spec.md`
4. API contract: `docs/04-api-contract.md`

## Quick Summary

- Primary goal: annotation-first person search and grounding tool.
- Core flow: search evidence -> build grounding versions and entity proposals -> annotate -> review.
- Inference is out of scope for this package; only prepared artifacts are ingested.
- Search uses a single MVP endpoint: `POST /search`.
- Fusion weights come only from saved search profiles.
- All collection endpoints use one cursor envelope: `items`, `cursor`, `limit`, `has_more`.

## Authority Import

Authority ingestion CLI now lives in `people-gator-common` as `people-gator-import-authorities`.

Run it from the common package:

```bash
cd ../people-gator-common
uv run people-gator-import-authorities --help
```
