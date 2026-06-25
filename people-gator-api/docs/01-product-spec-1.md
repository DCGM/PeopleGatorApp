# A product for PeopleGator API: Simpler overview of basic functionalities

Core concept is to define bare minimum system specs that define just the datamodel for annotations. We have the following requirements:
- Track person identities as the central entity
- Store named entity mentions found in text with location and model metadata
- Store face detections with keypoints and detection metadata
- Store descriptions from Wikidata or authority records
- Store alternative names from Wikidata or authorities
- Support 1-to-N relationships between identities and annotations
- Support N-to-N relationships for identity variants (future: identity relationship mechanism)

## 1. Introduction

This specification defines a simplified data model for person identification and annotation tracking. The system centers around **Identity** records that represent distinct persons, with all other annotation types linking to identities through flexible relationships.

### 1.1 Core Principles

1. **Identity-Centric Design** — All annotations (names, faces, descriptions, alternatives) relate to one or more identities.
2. **Flexible Relationships** — Support both 1-to-N (single identity) and N-to-N (multiple identity variants) mappings.
3. **Immutable Annotations** — Once created, annotation records are not modified; new versions are created for updates.
4. **Source Attribution** — Every annotation tracks its origin (model, authority, manual curation).

### 1.2 The API provides an interface for:

1. Create and manage person **Identities**
2. Add **Named Entities** (text mentions with locations)
3. Add **Detections** (face detections with keypoints)
4. Add **Descriptions** (biographical text from authorities)
5. Add **Alternative Names** (variant names from authorities)
6. Link annotations to identities (1-to-N or N-to-N)
7. Search identities by associated annotations

## 2. Core Data Architecture

### 2.0 IDs

IDs are globally unique identifiers using UUIDv6 format for time-ordered uniqueness.

- `clk_seq_hi_res` (8 bits): High 8 bits of per-node incrementing 16-bit sequence counter
- `clk_seq_low` (8 bits): Low 8 bits of per-node incrementing 16-bit sequence counter  
- `node` (48 bits): Unique node identifier, random value initialized at startup

### 2.1 Identity `IDENTITY`

> The central entity representing a distinct person. All annotations link to one or more identities.

| Field Name | Type | Description |
|------------|------|-------------|
| `identity_id` | UUID | Unique [UUIDv6](#20-ids) time-driven identifier for this identity. |
| `created_at` | TIMESTAMP | Creation timestamp of this identity record. |
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#28-principal-principal) who created this identity. |

Constraints:
- `identity_id` is unique across all identities.

Indices:
- `identity_id`
- `created_at`
- `principal_id`

### 2.2 Named Entity `NAMED_ENTITY`

> A named entity mention found in text, including location information and model metadata.

| Field Name | Type | Description |
|------------|------|-------------|
| `entity_id` | UUID | Unique [UUIDv6](#20-ids) time-driven identifier for this entity. |
| `text` | TEXT | The actual named entity text as found in the source. |
| `source_id` | UUID | [UUIDv6](#20-ids) of the [SOURCE](#27-source-source) where this entity was found. |
| `offset_start` | INTEGER | Character offset where the entity starts in the source text. |
| `offset_end` | INTEGER | Character offset where the entity ends in the source text. |
| `entity_type` | STRING | Type of entity (e.g., PERSON, ORGANIZATION, LOCATION). |
| `model_agent_id` | UUID | [UUIDv6](#20-ids) of the [MODEL_AGENT](#313-model-agent-model-agent) that detected this entity. |
| `confidence` | FLOAT | Confidence score of the entity detection (0.0 to 1.0). |
| `created_at` | TIMESTAMP | Creation timestamp of this entity record. |

Constraints:
- `entity_id` is unique across all named entities.

Indices:
- `entity_id`
- `source_id`
- `entity_type`
- `model_agent_id`
- `text` (for exact match lookups)

### 2.3 Detection `DETECTION`

> A face detection with bounding box, keypoints, and detection metadata.

| Field Name | Type | Description |
|------------|------|-------------|
| `detection_id` | UUID | Unique [UUIDv6](#20-ids) time-driven identifier for this detection. |
| `source_id` | UUID | [UUIDv6](#20-ids) of the [SOURCE](#27-source-source) (e.g., image) where face was detected. |
| `bounding_box` | JSON | Bounding box coordinates: `{"x": int, "y": int, "width": int, "height": int}`. |
| `keypoints` | JSON | Array of facial keypoints: `[{"type": "left_eye", "x": float, "y": float}, ...]`. |
| `model_agent_id` | UUID | [UUIDv6](#20-ids) of the [MODEL_AGENT](#313-model-agent-model-agent) that performed detection. |
| `confidence` | FLOAT | Confidence score of the detection (0.0 to 1.0). |
| `created_at` | TIMESTAMP | Creation timestamp of this detection record. |

Constraints:
- `detection_id` is unique across all detections.

Indices:
- `detection_id`
- `source_id`
- `model_agent_id`

### 2.4 Description `DESCRIPTION`

> Biographical or descriptive text from Wikidata, authorities, or other sources.

| Field Name | Type | Description |
|------------|------|-------------|
| `description_id` | UUID | Unique [UUIDv6](#20-ids) time-driven identifier for this description. |
| `text` | TEXT | The descriptive text content. |
| `source_type` | STRING | Type of source (e.g., WIKIDATA, AUTHORITY, MANUAL). |
| `source_ref` | STRING | Reference to external source (e.g., Wikidata Q-ID, authority ID). |
| `language` | STRING | ISO 639-1 language code of the description (e.g., "cs", "en"). |
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#28-principal-principal) who added this description. |
| `created_at` | TIMESTAMP | Creation timestamp of this description record. |

Constraints:
- `description_id` is unique across all descriptions.

Indices:
- `description_id`
- `source_type`
- `source_ref`
- `language`
- `principal_id`

### 2.5 Alternative Name `ALTERNATIVE_NAME`

> Variant names for a person from Wikidata, authorities, or other sources.

| Field Name | Type | Description |
|------------|------|-------------|
| `alt_name_id` | UUID | Unique [UUIDv6](#20-ids) time-driven identifier for this alternative name. |
| `name` | TEXT | The alternative name variant. |
| `name_type` | STRING | Type of name variant (e.g., BIRTH_NAME, PSEUDONYM, TRANSLITERATION, ABBREVIATION). |
| `source_type` | STRING | Type of source (e.g., WIKIDATA, AUTHORITY, MANUAL). |
| `source_ref` | STRING | Reference to external source (e.g., Wikidata Q-ID, authority ID). |
| `language` | STRING | ISO 639-1 language code of the name (e.g., "cs", "en"). |
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#28-principal-principal) who added this name. |
| `created_at` | TIMESTAMP | Creation timestamp of this name record. |

Constraints:
- `alt_name_id` is unique across all alternative names.

Indices:
- `alt_name_id`
- `name` (for exact and fuzzy match lookups)
- `name_type`
- `source_type`
- `source_ref`
- `language`
- `principal_id`

### 2.6 Identity Link `IDENTITY_LINK`

> Links annotations to identities, supporting both 1-to-N and N-to-N relationships.

| Field Name | Type | Description |
|------------|------|-------------|
| `link_id` | UUID | Unique [UUIDv6](#20-ids) time-driven identifier for this link. |
| `identity_id` | UUID | [UUIDv6](#20-ids) of the [IDENTITY](#21-identity-identity) being linked to. |
| `annotation_type` | STRING | Type of annotation being linked: `named_entity`, `detection`, `description`, `alternative_name`. |
| `annotation_id` | UUID | [UUIDv6](#20-ids) of the specific annotation record (entity_id, detection_id, etc.). |
| `confidence` | FLOAT | Confidence score of this link (0.0 to 1.0). |
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#28-principal-principal) who created this link. |
| `created_at` | TIMESTAMP | Creation timestamp of this link record. |

Constraints:
- `link_id` is unique across all identity links.
- Unique constraint on (`identity_id`, `annotation_type`, `annotation_id`) — same annotation cannot link to same identity multiple times.

Indices:
- `link_id`
- `identity_id`
- `annotation_type`
- `annotation_id`
- `principal_id`

### 2.7 Source `SOURCE`

> Metadata about the source document or media where annotations originate.

| Field Name | Type | Description |
|------------|------|-------------|
| `source_id` | UUID | Unique [UUIDv6](#20-ids) time-driven identifier. |
| `source_type` | STRING | Type of source (e.g., BOOK_PAGE, IMAGE, WEBPAGE, AUTHORITY_RECORD). |
| `uri` | TEXT | Uniform resource identifier for the source (URL, file path, etc.). |
| `metadata` | JSON | Source-specific metadata (e.g., page number, image dimensions, publication info). |
| `principal_id` | UUID | [UUIDv6](#20-ids) of the [PRINCIPAL](#28-principal-principal) who registered this source. |
| `created_at` | TIMESTAMP | Creation timestamp of this source record. |

Constraints:
- `source_id` is unique across all sources.
- Unique constraint on (`source_type`, `uri`) — same source cannot be registered multiple times.

Indices:
- `source_id`
- `source_type`
- `uri`
- `principal_id`

## 3. Extended Data Architecture

### 3.1 Principal Types

Principals are entities that create or modify records in the system. See [PRINCIPAL](#28-principal-principal) in the main specification for detailed types:

- **User** — Human users via OIDC authentication
- **Service Agent** — Automated services with code tracking
- **Model Agent** — ML models with registry metadata

### 3.2 Relationship Semantics

#### 3.2.1 1-to-N Relationships (Single Identity)

The most common case: an annotation links to exactly one identity.

```
IDENTITY (identity_id=I1)
  ├─ NAMED_ENTITY (entity_id=E1) via IDENTITY_LINK
  ├─ DETECTION (detection_id=D1) via IDENTITY_LINK
  ├─ DESCRIPTION (description_id=DS1) via IDENTITY_LINK
  └─ ALTERNATIVE_NAME (alt_name_id=AN1) via IDENTITY_LINK
```

#### 3.2.2 N-to-N Relationships (Identity Variants)

Multiple identities can link to the same annotation, representing uncertainty or variant interpretations:

```
ANNOTATION (e.g., NAMED_ENTITY E1)
  ├─ IDENTITY (I1) via IDENTITY_LINK L1 (confidence=0.8)
  ├─ IDENTITY (I2) via IDENTITY_LINK L2 (confidence=0.6)
  └─ IDENTITY (I3) via IDENTITY_LINK L3 (confidence=0.3)
```

This allows:
- **Uncertainty representation** — Multiple candidate identities with confidence scores
- **Variant tracking** — Different interpretations by different annotators
- **Evolution over time** — New links added as more evidence emerges

#### 3.2.3 Future: Identity Relationships

While not implemented in this version, future extensions may include:
- **Same-as relationships** — Linking identities believed to represent the same person
- **Hierarchical relationships** — Parent-child, family, organizational connections
- **Temporal relationships** — Identities valid in different time periods

## 4. Usage Examples

### 4.1 Creating a New Identity with Annotations

```
1. CREATE IDENTITY I1 (principal_id=P1)
2. CREATE NAMED_ENTITY E1 (text="Jan Neruda", source_id=S1, offset_start=42, offset_end=52)
3. CREATE IDENTITY_LINK L1 (identity_id=I1, annotation_type="named_entity", annotation_id=E1)
4. CREATE DETECTION D1 (source_id=S2, bounding_box={...}, keypoints=[...])
5. CREATE IDENTITY_LINK L2 (identity_id=I1, annotation_type="detection", annotation_id=D1)
6. CREATE ALTERNATIVE_NAME AN1 (name="Jan Nepomuk Neruda", name_type="BIRTH_NAME", source_type="WIKIDATA")
7. CREATE IDENTITY_LINK L3 (identity_id=I1, annotation_type="alternative_name", annotation_id=AN1)
```

### 4.2 Linking Multiple Identities to One Annotation

```
1. CREATE NAMED_ENTITY E1 (text="Neruda", source_id=S1, ...)
2. CREATE IDENTITY I1 (principal_id=P1)  -- Jan Neruda (poet)
3. CREATE IDENTITY I2 (principal_id=P1)  -- Jan Neruda (politician)
4. CREATE IDENTITY_LINK L1 (identity_id=I1, annotation_type="named_entity", annotation_id=E1, confidence=0.7)
5. CREATE IDENTITY_LINK L2 (identity_id=I2, annotation_type="named_entity", annotation_id=E1, confidence=0.3)
```

### 4.3 Search by Annotation

```
-- Find all identities linked to named entities containing "Neruda"
SELECT DISTINCT i.* 
FROM IDENTITY i
JOIN IDENTITY_LINK il ON i.identity_id = il.identity_id
JOIN NAMED_ENTITY ne ON il.annotation_id = ne.entity_id
WHERE il.annotation_type = 'named_entity'
  AND ne.text ILIKE '%Neruda%';

-- Find identities with face detections from a specific source
SELECT DISTINCT i.*
FROM IDENTITY i
JOIN IDENTITY_LINK il ON i.identity_id = il.identity_id
JOIN DETECTION d ON il.annotation_id = d.detection_id
WHERE il.annotation_type = 'detection'
  AND d.source_id = 'S2';
```

## 5. Implementation Notes

### 5.1 Immutability

All annotation records are immutable once created. Updates require:
1. Creating a new annotation record with updated data
2. Creating a new identity link to the new annotation
3. Optionally marking the old link as superseded (via metadata)

### 5.2 Confidence Scoring

Both annotations and identity links support confidence scores:
- **Annotation confidence** — How certain the model/detector is about the detection
- **Link confidence** — How certain we are that the annotation refers to this identity

### 5.3 Provenance Tracking

Every record tracks its origin:
- **Model agents** — Automated detections include model version and parameters
- **Principal agents** — Manual curation includes user/service identity
- **External sources** — Wikidata and authority references include source IDs

### 5.4 Indexing Strategy

Key indices for common query patterns:
- `IDENTITY_LINK(identity_id)` — Find all annotations for an identity
- `IDENTITY_LINK(annotation_type, annotation_id)` — Find all identities for an annotation
- `NAMED_ENTITY(text)` — Exact name lookups
- `ALTERNATIVE_NAME(name)` — Name variant searches
- `DETECTION(source_id)` — Find all faces in an image
- `DESCRIPTION(source_ref)` — Authority record lookups 