# A product for PeopleGator API: Simpler overview of basic functionalities

Core concept is to define bare minimum system specs that define just the data model shown in the ER diagram.

## 0. Core functionality

We want to facilitate search, addition of new mention and information, search for similar identities, and user modification of whether a mention was correctly assigned to some identity.

There are 2 types of user, a model or agent user, who automaticallu annotated pages in a document and triest to link them to the correct identity. And a human user, who can review the annotations and make corrections.

The agent can:
- Create a new document mention, mention and information
- Take a document mention, which is an aggregation of mentions and information, and link it to an identity
- Link a face detection to an identity

The user can:
- Retrieve and identity from a list
- Display document mentions for identity
- Check if document mention matches
- Display faces for identity
- Check if face matches
- Show similar identities based on current identity
- Merge identities

Low priority functionality for future user:
- Display mentions for identity
- Search for similar identities based on face, name, or description.



## 1. Introduction

This specification defines a simplified identity-centric annotation model.

The model includes:
- Identities as the central person record
- Mentions extracted from source text
- Information extracted at page/document level
- One document-level aggregator that groups mentions and information
- Face detections
- Descriptions
- Names
- Sources

## 2. Core Data Architecture

### 2.0 IDs

IDs are globally unique identifiers using UUIDv6 format.

### 2.1 Identity `IDENTITY`

> Central person record.

| Field Name | Type | Description |
|------------|------|-------------|
| `identity_id` | UUID | Unique identifier for the identity. |
| `principal_id` | UUID | Identifier of the principal that created the identity. |

### 2.2 Mention `MENTION`

> Text mention extracted from a source.

| Field Name | Type | Description |
|------------|------|-------------|
| `mention_id` | UUID | Unique identifier for the mention. |
| `text` | TEXT | Mention text span. |
| `offset_start` | INTEGER | Start character offset in source text. |
| `offset_end` | INTEGER | End character offset in source text. |
| `confidence` | FLOAT | Extraction confidence. |
| `source_id` | UUID | Source containing the mention. |
| `model_agent_id` | UUID | Model agent that extracted the mention. |

### 2.3 Information `INFORMATION`

> Relevant information extracted at page/document level.

| Field Name | Type | Description |
|------------|------|-------------|
| `information_id` | UUID | Unique identifier for the information record. |
| `text` | TEXT | Extracted information text. |
| `source_id` | UUID | Source containing the information. |
| `model_agent_id` | UUID | Model agent that extracted the information. |

### 2.4 Document Mention `DOCUMENT_MENTION`

> Single per-document aggregator that groups `MENTION` and `INFORMATION`.

| Field Name | Type | Description |
|------------|------|-------------|
| `document_mention_id` | UUID | Unique identifier for the document mention record. |
| `name` | STRING | Aggregated name value for the document-level record. |
| `information` | STRING | Aggregated information value for the document-level record. |
| `model_agent_id` | UUID | Model agent that produced the aggregation. |
| `identity_id` | UUID | Identity associated with this document-level record. |

### 2.5 Face `FACE`

> Face detection linked to an identity.

| Field Name | Type | Description |
|------------|------|-------------|
| `detection_id` | UUID | Unique identifier for the face detection. |
| `bounding_box` | JSON | Face bounding box coordinates. |
| `keypoints` | JSON | Facial keypoints. |
| `confidence` | FLOAT | Detection confidence. |
| `source_id` | UUID | Source containing the face detection. |
| `model_agent_id` | UUID | Model agent that performed detection. |
| `identity_id` | UUID | Identity associated with this face detection. |

### 2.6 Description `DESCRIPTION`

> Description text linked to an identity.

| Field Name | Type | Description |
|------------|------|-------------|
| `description_id` | UUID | Unique identifier for the description. |
| `text` | TEXT | Description text. |
| `language` | STRING | Language code. |
| `source_id` | UUID | Source containing the description. |
| `identity_id` | UUID | Identity associated with this description. |

### 2.7 Name `NAME`

> Name linked to an identity.

| Field Name | Type | Description |
|------------|------|-------------|
| `name_id` | UUID | Unique identifier for the name. |
| `name` | TEXT | Name value. |
| `source_id` | UUID | Source containing the name. |
| `identity_id` | UUID | Identity associated with this name. |

### 2.8 Source `SOURCE`

> Source document or media metadata.

| Field Name | Type | Description |
|------------|------|-------------|
| `source_id` | UUID | Unique identifier for the source. |
| `source_type` | STRING | Type of source. |
| `uri` | TEXT | Source URI. |
| `metadata` | JSON | Source metadata. |

## 3. Relationship Summary

- `PRINCIPAL` creates `IDENTITY`.
- `SOURCE` contains `MENTION`, `INFORMATION`, `DOCUMENT_MENTION`, and `FACE`.
- `DOCUMENT_MENTION` consists of `MENTION` and `INFORMATION`.
- `IDENTITY` has `DOCUMENT_MENTION`, `FACE`, `DESCRIPTION`, and `NAME`.

## 4. Entity Relationship Diagram

```mermaid
erDiagram
  PRINCIPAL ||--o{ IDENTITY : creates

  DOCUMENT_MENTION ||--o{ MENTION : consists_of
  DOCUMENT_MENTION ||--o{ INFORMATION : consists_of


  SOURCE ||--o{ MENTION : contains
  SOURCE ||--o{ INFORMATION : contains
  SOURCE ||--o{ DOCUMENT_MENTION : contains
  SOURCE ||--o{ FACE : contains

  IDENTITY ||--o{ DOCUMENT_MENTION : has
  IDENTITY ||--o{ FACE : has
  IDENTITY ||--o{ DESCRIPTION : has
  IDENTITY ||--o{ NAME : has

  IDENTITY {
    uuid identity_id
    uuid principal_id
  }

  MENTION {
    uuid mention_id
    text text
    int offset_start
    int offset_end
    float confidence
    uuid source_id
    uuid model_agent_id
  }

  INFORMATION {
    uuid information_id
    text text
    uuid source_id
    uuid model_agent_id
  }

  DOCUMENT_MENTION {
    uuid document_mention_id
    string name
    string information
    uuid model_agent_id
    uuid identity_id
  }

  FACE {
    uuid detection_id
    json bounding_box
    json keypoints
    float confidence
    uuid source_id
    uuid model_agent_id
    uuid identity_id
  }

  DESCRIPTION {
    uuid description_id
    text text
    string language
    uuid source_id
    uuid identity_id
  }

  NAME {
    uuid name_id
    text name
    uuid source_id
    uuid identity_id
  }

  SOURCE {
    uuid source_id
    string source_type
    text uri
    json metadata
  }
```
