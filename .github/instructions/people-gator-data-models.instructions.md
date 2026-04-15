---
description: "Use when implementing or refactoring People Gator data ingestion, retrieval, or APIs that touch annotation, detection, OCR layout, or named entity records. Enforces canonical schema names, coordinate semantics, and typed Pydantic models."
name: "People Gator Data Models"
---
# People Gator Data Models

- Treat README data structures as canonical source fields for:
  - `PeopleGatorAnnotation`
  - `PeopleGatorDetection`
  - `PeopleGatorNamedEntitySpan`
  - `PeopleGatorNamedEntity`
  - `PeroLine`
  - `PeroRegion`
  - `PeroLayout`

- Keep model classes typed and explicit using Pydantic models.
- Do not silently rename canonical fields from source records.
- If introducing internal aliases, keep import/export converters explicit and lossless.

# Coordinate And Geometry Rules

- Preserve page-space coordinates (`page_left`, `page_top`, `page_width`, `page_height`) as page-relative values.
- Keep keypoints in documented order: `[left_eye, right_eye, nose, left_mouth_corner, right_mouth_corner]`.
- Keep polygon and baseline points ordered and stable; do not reorder unless a conversion step is explicitly documented.

# Identity And Provenance Rules

- Preserve provenance keys (`library`, `document`, `page`) across transformations.
- Keep image linkage identifiers (`image_name`, `crop_name`) unchanged unless there is an explicit migration.
- For any output candidate, include best-available source context (`library`, `document`, `page`).

# Validation And Compatibility

- Use strict field typing for dimensions, coordinates, confidence scores, and probability scores.
- Use `str | None` for nullable text fields instead of untyped optional values.
- When schema evolution is required, add versioned migration logic and backward-compatible readers.

# Do Not

- Do not drop provenance fields during preprocessing or embedding pipeline stages.
- Do not mix image-space and page-space coordinates in the same field.
- Do not return ad hoc dictionaries where typed models are expected.