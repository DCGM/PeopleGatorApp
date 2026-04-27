# Entity-Relationship Diagrams

This document keeps the data model intentionally simple and split into focused diagrams.

## 1. Master Entity and Grounding Versions

```mermaid
erDiagram
      MASTER_ENTITY ||--o{ GROUNDING_VERSION : has
      GROUNDING_VERSION ||--o{ GROUNDING_CANDIDATE : includes
      GROUNDING_VERSION ||--o{ GROUNDING_NAME : includes
      GROUNDING_VERSION ||--o{ GROUNDING_PHOTO : includes
      GROUNDING_CANDIDATE }o--|| SOURCE : from
      GROUNDING_NAME }o--|| SOURCE : from
      GROUNDING_PHOTO }o--|| SOURCE : from

      MASTER_ENTITY {
         uuid master_entity_id PK
         string canonical_display_name
         string status
         datetime created_at
         datetime updated_at
      }

      GROUNDING_VERSION {
         uuid grounding_version_id PK
         uuid master_entity_id FK
         int version
         string lifecycle_state
         float confidence
         string notes
         datetime created_at
      }

      GROUNDING_CANDIDATE {
         uuid candidate_id PK
         uuid grounding_version_id FK
         string scheme
         string value
         string state
         float confidence
         uuid source_id FK
      }

      GROUNDING_NAME {
         uuid grounding_name_id PK
         uuid grounding_version_id FK
         string text
         string language_tag
         bool is_primary
         float confidence
         uuid source_id FK
      }

      GROUNDING_PHOTO {
         uuid grounding_photo_id PK
         uuid grounding_version_id FK
         string asset_path
         string content_hash
         float quality_score
         uuid source_id FK
      }

      SOURCE {
         uuid source_id PK
         string provider
         string library
         string document
         int page
         string uri
      }
```

## 2. Entity Proposal and Evidence Acquisition

```mermaid
erDiagram
      MASTER_ENTITY ||--o{ ENTITY_PROPOSAL : context_for
      ENTITY_PROPOSAL ||--o{ PROPOSAL_NAME : has
      ENTITY_PROPOSAL ||--o{ PROPOSAL_GROUNDING : has
      ENTITY_PROPOSAL ||--o{ PROPOSAL_EVIDENCE : links
      PROPOSAL_EVIDENCE }o--|| EVIDENCE_ITEM : references
      EVIDENCE_ITEM }o--|| SOURCE : from

      ENTITY_PROPOSAL {
         uuid proposal_id PK
         uuid master_entity_id FK
         string title
         string status
         datetime created_at
      }

      PROPOSAL_NAME {
         uuid proposal_name_id PK
         uuid proposal_id FK
         string text
         string language_tag
         float confidence
      }

      PROPOSAL_GROUNDING {
         uuid proposal_grounding_id PK
         uuid proposal_id FK
         string scheme
         string value
         float confidence
         string state
      }

      EVIDENCE_ITEM {
         uuid evidence_id PK
         string evidence_type
         string polarity
         string content_ref
         uuid source_id FK
         datetime created_at
      }

      PROPOSAL_EVIDENCE {
         uuid proposal_evidence_id PK
         uuid proposal_id FK
         uuid evidence_id FK
         float confidence
      }

      SOURCE {
         uuid source_id PK
         string provider
         string library
         string document
         int page
         string uri
      }
```

`EVIDENCE_ITEM.polarity` is constrained to `positive` or `negative`.

## 3. Annotation, Review, and Removal Log

```mermaid
erDiagram
      ENTITY_PROPOSAL ||--o{ ANNOTATION_INSTANCE : base_for
      ANNOTATION_INSTANCE ||--o{ ANNOTATION_INSTANCE : revision_of
      ANNOTATION_INSTANCE ||--o| ANNOTATED_ENTITY : produces
      ANNOTATION_INSTANCE ||--o| REVIEW_INSTANCE : reviewed_by
      REMOVAL_LOG }o--|| ANNOTATION_INSTANCE : can_reference
      REMOVAL_LOG }o--|| ANNOTATED_ENTITY : can_reference
      REMOVAL_LOG }o--|| REVIEW_INSTANCE : can_reference

      ENTITY_PROPOSAL {
         uuid proposal_id PK
         string status
      }

      ANNOTATION_INSTANCE {
         uuid annotation_instance_id PK
         uuid proposal_id FK
         uuid previous_instance_id FK
         int revision
         string annotator_id
         string status
         datetime created_at
         datetime updated_at
      }

      ANNOTATED_ENTITY {
         uuid annotated_entity_id PK
         uuid annotation_instance_id FK
         uuid master_entity_id FK
         string selected_name
         string selected_grounding
         datetime created_at
      }

      REVIEW_INSTANCE {
         uuid review_instance_id PK
         uuid annotation_instance_id FK
         string reviewer_id
         string decision
         string status
         datetime reviewed_at
      }

      REMOVAL_LOG {
         uuid removal_log_id PK
         string target_type
         uuid target_id
         string reason
         string removed_by
         datetime removed_at
      }
```

Rules:

1. `ENTITY_PROPOSAL` is the baseline and remains preserved.
2. Updates create new `ANNOTATION_INSTANCE` revisions rather than overwriting earlier rows.
3. Each annotation instance is reviewable.
4. Removals are soft and recorded in `REMOVAL_LOG`.
