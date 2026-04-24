# people-gator-api

Backend service for People Gator.

This repository now keeps specification content in three focused documents to avoid contradictions between product goals, architecture choices, and API contracts:

1. Product specification: `docs/01-product-spec.md`
2. Architecture specification: `docs/02-architecture-spec.md`
3. API contract: `docs/03-api-contract.md`

## Quick Summary

- Primary goal: annotation-first person search and grounding tool.
- Core flow: search evidence -> create or update grounded person entities -> annotate -> review.
- Inference is out of scope for this package; only prepared artifacts are ingested.
- Search uses a single MVP endpoint: `POST /search`.
- Fusion weights come only from saved search profiles.
- All collection endpoints use one cursor envelope: `items`, `cursor`, `limit`, `has_more`.
