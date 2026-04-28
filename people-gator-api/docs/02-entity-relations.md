# Entity-Relationship Diagrams

This document keeps the data model intentionally simple and split into focused diagrams.

## 1. Master Entity and Grounding Versions

```mermaid
erDiagram
      MASTER_ENTITY ||--o{ GROUNDING_VERSION : has
      GROUNDING_VERSION ||--o{ GROUNDING_VERSION_RECORD_LINK : has
      GROUNDING_RECORD ||--o{ GROUNDING_VERSION_RECORD_LINK : links
      GROUNDING_RECORD ||--o| GROUNDING_IDENTIFIER : typed_as
      GROUNDING_RECORD ||--o| GROUNDING_NATIONALITY : typed_as
      GROUNDING_RECORD ||--o| GROUNDING_NAME : typed_as
      GROUNDING_RECORD ||--o| GROUNDING_TEXT : typed_as
      GROUNDING_RECORD ||--o| GROUNDING_PHOTO : typed_as
      GROUNDING_PHOTO ||--o{ GROUNDING_FACE_DETECTION : has

      SOURCE_PROVIDER ||--o{ GROUNDING_RECORD : provides

      MASTER_ENTITY {
         uuid master_entity_id PK
         uuid current_grounding_version_id FK
      }

      GROUNDING_VERSION {
         uuid grounding_version_id PK
         uuid master_entity_id FK
         datetime  birth_date
         datetime  death_date
         int revision
         string state
         datetime created_at
         datetime updated_at
      }

      GROUNDING_VERSION_RECORD_LINK {
         uuid grounding_version_id PK, FK
         uuid grounding_record_id PK, FK
      }

      GROUNDING_RECORD {
         uuid grounding_record_id PK
         uuid grounding_version_id FK
         string record_type
         string source_provider FK
         string source_uri
      }

      GROUNDING_IDENTIFIER {
         uuid grounding_record_id PK, FK
         string value
         string scheme
         datetime asserted_at
         string asserted_by
      }

      GROUNDING_NATIONALITY {
         uuid grounding_record_id PK, FK
         string country_name
         string language
         datetime asserted_at
         string asserted_by
      }

      GROUNDING_NAME {
         uuid grounding_record_id PK, FK
         string name
         string language
      }

      GROUNDING_TEXT {
         uuid grounding_record_id PK, FK
         string text
         string language
      }

      GROUNDING_PHOTO {
         uuid grounding_record_id PK, FK
         string local_asset_path
         string mime_type
         string content_hash
      }

      GROUNDING_FACE_DETECTION {
         uuid grounding_record_id PK, FK
         uuid parent_photo_grounding_record_id FK
         json metadata
      }

      SOURCE_PROVIDER {
         string name PK
         string description
      }
```

## 2. Entity Proposal and Evidence Acquisition

```mermaid
erDiagram
      ENTITY_PROPOSAL ||--o{ PROPOSAL_GROUNDING : has
      GROUNDING_VERSION ||--o{ PROPOSAL_GROUNDING : supports
      ENTITY_PROPOSAL ||--o{ PROPOSAL_EVIDENCE : links
      PROPOSAL_EVIDENCE }o--|| EVIDENCE : references
      EVIDENCE }o--|| SOURCE_PROVIDER : from

      EVIDENCE ||--o| EVIDENCE_PHOTO : typed_as
      EVIDENCE ||--o| EVIDENCE_FACE_DETECTION : typed_as
      EVIDENCE ||--o| EVIDENCE_TEXT_REGION : typed_as
      EVIDENCE ||--o| EVIDENCE_PHOTO_DETECTION : typed_as


      ENTITY_PROPOSAL {
         uuid proposal_id PK
         uuid master_entity_id FK
         string status
         datetime created_at
      }
      
      PROPOSAL_GROUNDING {
         uuid proposal_grounding_id PK
         uuid grounding_version_id FK
         uuid proposal_id FK
      }

      PROPOSAL_EVIDENCE {
         uuid proposal_evidence_id PK
         uuid proposal_id FK
         uuid evidence_id FK
      }
      
      EVIDENCE {
         uuid evidence_id PK
         string evidence_type
         string source_provider FK
         string source_uri
      }

      EVIDENCE_PHOTO {
         uuid evidence_id PK, FK
         int image_width
         int image_height
         string mime_type
      }

      EVIDENCE_FACE_DETECTION {
         uuid evidence_id PK, FK
         uuid parent_photo_evidence_id FK
         json metadata
      }

      EVIDENCE_PHOTO_DETECTION {
         uuid evidence_id PK, FK
         uuid parent_photo_evidence_id FK
         json metadata
      }
      
      EVIDENCE_TEXT_REGION {
         uuid evidence_id PK, FK
         string text
         string language
         json metadata
      }
```

## 3. Annotation, Review, and Removal Log

```mermaid
erDiagram
      USER ||--o{ ANNOTATION_INSTANCE : annotates
      ANNOTATION_INSTANCE ||--o{ REVIEW_INSTANCE : has
      USER ||--o{ REVIEW_INSTANCE : reviews
      ANNOTATION_INSTANCE ||--o{ ACTION_LOG : logs
      REVIEW_INSTANCE ||--o{ ACTION_LOG : logs
      EVIDENCE ||--o{ ACTION_LOG : has_removal
      EVIDENCE ||--o{ ACTION_LOG : has_addition
      GROUNDING_RECORD ||--o{ ACTION_LOG : has_removal
      GROUNDING_RECORD ||--o{ ACTION_LOG : has_addition

      ANNOTATION_INSTANCE {
         uuid annotation_instance_id PK
         uuid proposal_id FK
         uuid annotator_id FK
         string status
         datetime updated_at
      }

      REVIEW_INSTANCE {
         uuid review_instance_id PK
         uuid annotation_instance_id FK
         uuid reviewer_id FK
         string status
         datetime reviewed_at
      }

      ACTION_LOG {
         uuid action_log_id PK
         uuid action_by FK
         uuid annotation_instance_id FK
         uuid review_instance_id FK
         uuid removed_evidence_id FK
         uuid added_evidence_id FK
         uuid removed_grounding_id FK
         uuid added_grounding_id FK
         datetime action_at
      }
```

## 4. User and Role Management

```mermaid
erDiagram
      USER ||--o{ USER_ROLE : has
      ROLE ||--o{ USER_ROLE : assigned_to
      USER ||--o{ AUTH_IDENTITY : authenticates_with
      
      USER {
         uuid user_id PK
         string username
         string email
         string full_name
         string status
         string refresh_token
         datetime created_at
         datetime updated_at
      }

      ROLE {
         uuid role_id PK
         string role_name
         string description
      }

      USER_ROLE {
         uuid user_role_id PK
         uuid user_id FK
         uuid role_id FK
         datetime assigned_at
      }

      AUTH_IDENTITY {
         uuid auth_identity_id PK
         uuid user_id FK
         string provider
         string provider_subject
         string provider_email
         string provider_username
         datetime last_login_at
         datetime created_at
      }
```

