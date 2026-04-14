---
description: "Use when planning or implementing People Gator retrieval, identity matching, and search features over library data. Covers outputs, person search priorities, and domain constraints."
name: "People Gator Search Guidance"
---
# People Gator Search Guidance

- Prioritize people search features:
  - search by person name,
  - search by uploaded image,
  - combined search by text, image, and name,
  - grouping known and unknown individuals.

# Result Expectations

- Return person photos as the primary output.
- Include best-available identity hypothesis.
- Include source context for each match (library, document, page) when available.

# Retrieval And Matching

- Prefer robust multi-signal retrieval logic when practical:
  - name similarity,
  - face similarity,
  - OCR or NER context,
  - metadata context.
- Candidate generation plus reranking is recommended for noisy, large corpora but not mandatory.

# Domain Constraints

- Account for Czech and historical name variation (inflections, aliases, spelling variants, transliteration).
- Handle low-quality historical scans and face detection uncertainty in matching pipelines.
