"""Replace JSON snapshots with typed resource history, preserving existing previews."""

from alembic import op

revision = "d34a021b0016"
down_revision = "d34a021b0015"
branch_labels = None
depends_on = None

DDL = [
    """CREATE TABLE pg_demo_entity_history (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	last_touched_at TIMESTAMP WITH TIME ZONE, 
	last_touched_by_user_id UUID, 
	last_touched_by_api_key_id UUID, 
	thumbnail_face_id UUID, 
	thumbnail_mode VARCHAR(16) NOT NULL, 
	kind VARCHAR(64), 
	name TEXT, 
	name_normalized TEXT, 
	description TEXT, 
	short_description TEXT, 
	wikidata_id VARCHAR(64), 
	nlcr_authority_id VARCHAR(128), 
	search_document TSVECTOR NOT NULL, 
	version INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE, 
	created_by_user_id UUID, 
	created_by_api_key_id UUID, 
	deleted BOOLEAN NOT NULL, 
	change_id UUID NOT NULL, 
	PRIMARY KEY (id, version), 
	CONSTRAINT ck_pg_demo_entity_history_version CHECK (version >= 1), 
	CONSTRAINT ck_pg_demo_entity_history_entities_person_thumbnail CHECK (kind = 'person' OR (thumbnail_face_id IS NULL AND thumbnail_mode = 'automatic')), 
	CONSTRAINT ck_pg_demo_entity_history_entities_thumbnail_mode CHECK (thumbnail_mode IN ('automatic', 'manual')), 
	CONSTRAINT ck_pg_demo_entity_history_entities_manual_thumbnail CHECK (thumbnail_mode <> 'manual' OR thumbnail_face_id IS NOT NULL), 
	FOREIGN KEY(change_id) REFERENCES pg_demo_audit_changes (id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_pg_demo_entity_history_change_id ON pg_demo_entity_history (change_id)""",
    """CREATE INDEX ix_pg_demo_entity_history_last_touched_at ON pg_demo_entity_history (last_touched_at)""",
    """CREATE INDEX ix_pg_demo_entity_history_last_touched_by_user_id ON pg_demo_entity_history (last_touched_by_user_id)""",
    """CREATE TABLE pg_demo_face_history (
	id UUID NOT NULL, 
	source_id UUID NOT NULL, 
	entity_id UUID, 
	entity_link_state pg_demo_entity_link_state, 
	entity_link_verified_by_user_id UUID, 
	entity_link_verified_at TIMESTAMP WITH TIME ZONE, 
	occurrence_type VARCHAR(32) NOT NULL, 
	roi JSONB NOT NULL, 
	version INTEGER NOT NULL, 
	last_touched_at TIMESTAMP WITH TIME ZONE, 
	last_touched_by_user_id UUID, 
	last_touched_by_api_key_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE, 
	created_by_user_id UUID, 
	created_by_api_key_id UUID, 
	user_id UUID NOT NULL, 
	identifier TEXT, 
	confidence FLOAT NOT NULL, 
	keypoints FLOAT[][] NOT NULL, 
	keypoint_types VARCHAR[] NOT NULL, 
	deleted BOOLEAN NOT NULL, 
	change_id UUID NOT NULL, 
	PRIMARY KEY (id, version), 
	CONSTRAINT ck_pg_demo_face_history_version CHECK (version >= 1), 
	CONSTRAINT ck_pg_demo_face_history_image_occurrences_link CHECK ((entity_id IS NULL) = (entity_link_state IS NULL)), 
	CONSTRAINT ck_pg_demo_face_history_image_occurrences_verification CHECK ((entity_link_state IS NOT DISTINCT FROM 'verified' AND entity_link_verified_by_user_id IS NOT NULL AND entity_link_verified_at IS NOT NULL) OR (entity_link_state IS DISTINCT FROM 'verified' AND entity_link_verified_by_user_id IS NULL AND entity_link_verified_at IS NULL)), 
	CONSTRAINT ck_pg_demo_face_history_image_occurrences_touch CHECK ((last_touched_at IS NULL AND last_touched_by_user_id IS NULL AND last_touched_by_api_key_id IS NULL) OR (last_touched_at IS NOT NULL AND last_touched_by_user_id IS NOT NULL)), 
	CONSTRAINT ck_pg_demo_face_history_face_five_2d_keypoints CHECK (array_ndims(keypoints) = 2
            AND array_length(keypoints, 1) = 5
            AND array_length(keypoints, 2) = 2), 
	CONSTRAINT ck_pg_demo_face_history_face_five_keypoint_types CHECK (cardinality(keypoint_types) = 5), 
	FOREIGN KEY(change_id) REFERENCES pg_demo_audit_changes (id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_pg_demo_face_history_change_id ON pg_demo_face_history (change_id)""",
    """CREATE INDEX ix_pg_demo_face_history_entity_id ON pg_demo_face_history (entity_id)""",
    """CREATE INDEX ix_pg_demo_face_history_entity_link_state ON pg_demo_face_history (entity_link_state)""",
    """CREATE INDEX ix_pg_demo_face_history_entity_link_verified_at ON pg_demo_face_history (entity_link_verified_at)""",
    """CREATE INDEX ix_pg_demo_face_history_entity_link_verified_by_user_id ON pg_demo_face_history (entity_link_verified_by_user_id)""",
    """CREATE INDEX ix_pg_demo_face_history_last_touched_at ON pg_demo_face_history (last_touched_at)""",
    """CREATE INDEX ix_pg_demo_face_history_last_touched_by_user_id ON pg_demo_face_history (last_touched_by_user_id)""",
    """CREATE INDEX ix_pg_demo_face_history_source_id ON pg_demo_face_history (source_id)""",
    """CREATE TABLE pg_demo_text_mention_history (
	id UUID NOT NULL, 
	source_id UUID NOT NULL, 
	entity_id UUID, 
	entity_link_state pg_demo_entity_link_state, 
	entity_link_verified_by_user_id UUID, 
	entity_link_verified_at TIMESTAMP WITH TIME ZONE, 
	mention TEXT NOT NULL, 
	mention_normalized TEXT NOT NULL, 
	context TEXT, 
	version INTEGER NOT NULL, 
	last_touched_at TIMESTAMP WITH TIME ZONE, 
	last_touched_by_user_id UUID, 
	last_touched_by_api_key_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE, 
	created_by_user_id UUID, 
	created_by_api_key_id UUID, 
	deleted BOOLEAN NOT NULL, 
	change_id UUID NOT NULL, 
	PRIMARY KEY (id, version), 
	CONSTRAINT ck_pg_demo_text_mention_history_version CHECK (version >= 1), 
	CONSTRAINT ck_pg_demo_text_mention_history_text_mentions_verification CHECK ((entity_link_state IS NOT DISTINCT FROM 'verified' AND entity_link_verified_by_user_id IS NOT NULL AND entity_link_verified_at IS NOT NULL) OR (entity_link_state IS DISTINCT FROM 'verified' AND entity_link_verified_by_user_id IS NULL AND entity_link_verified_at IS NULL)), 
	CONSTRAINT ck_pg_demo_text_mention_history_text_mentions_link CHECK ((entity_id IS NULL) = (entity_link_state IS NULL)), 
	CONSTRAINT ck_pg_demo_text_mention_history_text_mentions_touch CHECK ((last_touched_at IS NULL AND last_touched_by_user_id IS NULL AND last_touched_by_api_key_id IS NULL) OR (last_touched_at IS NOT NULL AND last_touched_by_user_id IS NOT NULL)), 
	FOREIGN KEY(change_id) REFERENCES pg_demo_audit_changes (id) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_pg_demo_text_mention_history_change_id ON pg_demo_text_mention_history (change_id)""",
    """CREATE INDEX ix_pg_demo_text_mention_history_entity_id ON pg_demo_text_mention_history (entity_id)""",
    """CREATE INDEX ix_pg_demo_text_mention_history_entity_link_state ON pg_demo_text_mention_history (entity_link_state)""",
    """CREATE INDEX ix_pg_demo_text_mention_history_entity_link_verified_at ON pg_demo_text_mention_history (entity_link_verified_at)""",
    """CREATE INDEX ix_pg_demo_text_mention_history_entity_link_verified_by_user_id ON pg_demo_text_mention_history (entity_link_verified_by_user_id)""",
    """CREATE INDEX ix_pg_demo_text_mention_history_last_touched_at ON pg_demo_text_mention_history (last_touched_at)""",
    """CREATE INDEX ix_pg_demo_text_mention_history_last_touched_by_user_id ON pg_demo_text_mention_history (last_touched_by_user_id)""",
    """CREATE INDEX ix_pg_demo_text_mention_history_source_id ON pg_demo_text_mention_history (source_id)""",
    """CREATE TABLE pg_demo_source_history (
	id UUID NOT NULL, 
	last_touched_at TIMESTAMP WITH TIME ZONE, 
	last_touched_by_user_id UUID, 
	last_touched_by_api_key_id UUID, 
	url TEXT NOT NULL, 
	source_type VARCHAR(32) NOT NULL, 
	version INTEGER NOT NULL, 
	library VARCHAR(255), 
	document_id UUID, 
	page_id UUID, 
	page_number INTEGER, 
	name TEXT, 
	name_normalized TEXT, 
	deleted BOOLEAN NOT NULL, 
	change_id UUID NOT NULL, 
	PRIMARY KEY (id, version), 
	CONSTRAINT ck_pg_demo_source_history_version CHECK (version >= 1), 
	CONSTRAINT ck_pg_demo_source_history_sources_touch CHECK ((last_touched_at IS NULL AND last_touched_by_user_id IS NULL AND last_touched_by_api_key_id IS NULL) OR (last_touched_at IS NOT NULL AND last_touched_by_user_id IS NOT NULL)), 
	CONSTRAINT ck_pg_demo_source_history_pages_page_number CHECK (page_number > 0), 
	FOREIGN KEY(change_id) REFERENCES pg_demo_audit_changes (id) ON DELETE RESTRICT, 
	CONSTRAINT ck_pg_demo_source_history_subtype CHECK (source_type IN ('page', 'document', 'image') AND (source_type NOT IN ('page', 'document') OR (library IS NOT NULL AND document_id IS NOT NULL)) AND (source_type <> 'page' OR page_id IS NOT NULL))
)""",
    """CREATE INDEX ix_pg_demo_source_history_change_id ON pg_demo_source_history (change_id)""",
    """CREATE INDEX ix_pg_demo_source_history_document_id ON pg_demo_source_history (document_id)""",
    """CREATE INDEX ix_pg_demo_source_history_last_touched_at ON pg_demo_source_history (last_touched_at)""",
    """CREATE INDEX ix_pg_demo_source_history_last_touched_by_user_id ON pg_demo_source_history (last_touched_by_user_id)""",
    """CREATE INDEX ix_pg_demo_source_history_library ON pg_demo_source_history (library)""",
    """CREATE INDEX ix_pg_demo_source_history_page_id ON pg_demo_source_history (page_id)""",
    """CREATE INDEX ix_pg_demo_source_history_source_type ON pg_demo_source_history (source_type)""",
    """CREATE TABLE pg_demo_alias_history (
	id UUID NOT NULL, 
	entity_id UUID NOT NULL, 
	name TEXT NOT NULL, 
	name_normalized TEXT NOT NULL, 
	search_document TSVECTOR NOT NULL, 
	version INTEGER NOT NULL, 
	PRIMARY KEY (id, version), 
	CONSTRAINT ck_pg_demo_alias_history_version CHECK (version >= 1), 
	FOREIGN KEY(entity_id, version) REFERENCES pg_demo_entity_history (id, version) ON DELETE RESTRICT
)""",
    """CREATE INDEX ix_pg_demo_alias_history_entity_id ON pg_demo_alias_history (entity_id)""",
    """CREATE TABLE pg_demo_face_embedding_history (
	face_id UUID NOT NULL, 
	version INTEGER NOT NULL, 
	model_id VARCHAR(255) NOT NULL, 
	embedding VECTOR NOT NULL, 
	PRIMARY KEY (face_id, version, model_id), 
	FOREIGN KEY(face_id, version) REFERENCES pg_demo_face_history (id, version) ON DELETE RESTRICT
)""",
]


def upgrade():
    for statement in DDL:
        op.execute(statement)
    op.execute("""INSERT INTO pg_demo_entity_history (id, user_id, last_touched_at, last_touched_by_user_id, last_touched_by_api_key_id, thumbnail_face_id, thumbnail_mode, kind, name, name_normalized, description, short_description, wikidata_id, nlcr_authority_id, search_document, version, created_at, created_by_user_id, created_by_api_key_id, deleted, change_id)
        SELECT r.id, r.user_id, r.last_touched_at, r.last_touched_by_user_id, r.last_touched_by_api_key_id, r.thumbnail_face_id, r.thumbnail_mode, r.kind, r.name, r.name_normalized, r.description, r.short_description, r.wikidata_id, r.nlcr_authority_id, r.search_document, r.version, r.created_at, r.created_by_user_id, r.created_by_api_key_id, r.deleted, r.change_id FROM pg_demo_object_history h,
        LATERAL jsonb_populate_record(NULL::pg_demo_entity_history, h.state ||
            jsonb_build_object('change_id', h.change_id, 'deleted', h.deleted)) r
        WHERE h.object_type = 'entity'""")
    op.execute("""INSERT INTO pg_demo_face_history (id, source_id, entity_id, entity_link_state, entity_link_verified_by_user_id, entity_link_verified_at, occurrence_type, roi, version, last_touched_at, last_touched_by_user_id, last_touched_by_api_key_id, created_at, created_by_user_id, created_by_api_key_id, user_id, identifier, confidence, keypoints, keypoint_types, deleted, change_id)
        SELECT r.id, r.source_id, r.entity_id, r.entity_link_state, r.entity_link_verified_by_user_id, r.entity_link_verified_at, r.occurrence_type, r.roi, r.version, r.last_touched_at, r.last_touched_by_user_id, r.last_touched_by_api_key_id, r.created_at, r.created_by_user_id, r.created_by_api_key_id, r.user_id, r.identifier, r.confidence, r.keypoints, r.keypoint_types, r.deleted, r.change_id FROM pg_demo_object_history h,
        LATERAL jsonb_populate_record(NULL::pg_demo_face_history, h.state ||
            jsonb_build_object('change_id', h.change_id, 'deleted', h.deleted)) r
        WHERE h.object_type = 'face'""")
    op.execute("""INSERT INTO pg_demo_text_mention_history (id, source_id, entity_id, entity_link_state, entity_link_verified_by_user_id, entity_link_verified_at, mention, mention_normalized, context, version, last_touched_at, last_touched_by_user_id, last_touched_by_api_key_id, created_at, created_by_user_id, created_by_api_key_id, deleted, change_id)
        SELECT r.id, r.source_id, r.entity_id, r.entity_link_state, r.entity_link_verified_by_user_id, r.entity_link_verified_at, r.mention, r.mention_normalized, r.context, r.version, r.last_touched_at, r.last_touched_by_user_id, r.last_touched_by_api_key_id, r.created_at, r.created_by_user_id, r.created_by_api_key_id, r.deleted, r.change_id FROM pg_demo_object_history h,
        LATERAL jsonb_populate_record(NULL::pg_demo_text_mention_history, h.state ||
            jsonb_build_object('change_id', h.change_id, 'deleted', h.deleted)) r
        WHERE h.object_type = 'mention'""")
    op.execute("""INSERT INTO pg_demo_source_history (id, last_touched_at, last_touched_by_user_id, last_touched_by_api_key_id, url, source_type, version, library, document_id, page_id, page_number, name, name_normalized, deleted, change_id)
        SELECT r.id, r.last_touched_at, r.last_touched_by_user_id, r.last_touched_by_api_key_id, r.url, r.source_type, r.version, r.library, r.document_id, r.page_id, r.page_number, r.name, r.name_normalized, r.deleted, r.change_id FROM pg_demo_object_history h,
        LATERAL jsonb_populate_record(NULL::pg_demo_source_history, h.state ||
            jsonb_build_object('change_id', h.change_id, 'deleted', h.deleted)) r
        WHERE h.object_type = 'source'""")
    op.execute("""INSERT INTO pg_demo_alias_history (id, entity_id, name, name_normalized, search_document, version)
        SELECT r.id, r.entity_id, r.name, r.name_normalized, r.search_document, r.version FROM pg_demo_object_history h,
        LATERAL jsonb_array_elements(h.state->'aliases') item,
        LATERAL jsonb_populate_record(NULL::pg_demo_alias_history, item || jsonb_build_object('version', h.version)) r
        WHERE h.object_type = 'entity'""")
    op.execute("""INSERT INTO pg_demo_face_embedding_history (face_id, version, model_id, embedding)
        SELECT r.face_id, r.version, r.model_id, r.embedding FROM pg_demo_object_history h,
        LATERAL jsonb_array_elements(h.state->'embeddings') item,
        LATERAL jsonb_populate_record(NULL::pg_demo_face_embedding_history, item || jsonb_build_object('version', h.version)) r
        WHERE h.object_type = 'face'""")
    op.drop_table("pg_demo_object_history")


def downgrade():
    op.execute("""CREATE TABLE pg_demo_object_history (
        object_type varchar(16) NOT NULL, object_id uuid NOT NULL,
        version integer NOT NULL, change_id uuid NOT NULL REFERENCES pg_demo_audit_changes(id) ON DELETE RESTRICT,
        deleted boolean NOT NULL, entity_id uuid, source_id uuid, state jsonb NOT NULL,
        PRIMARY KEY (object_type, object_id, version))""")
    for field in ("change_id", "entity_id", "source_id"):
        op.create_index(
            "ix_pg_demo_object_history_" + field, "pg_demo_object_history", [field]
        )
    for kind, table in (
        ("entity", "entity"),
        ("face", "face"),
        ("mention", "text_mention"),
        ("source", "source"),
    ):
        extras = "'{}'::jsonb"
        if kind == "entity":
            extras = "jsonb_build_object('aliases', COALESCE((SELECT jsonb_agg(to_jsonb(a) - 'version' ORDER BY a.name) FROM pg_demo_alias_history a WHERE a.entity_id=h.id AND a.version=h.version), '[]'::jsonb))"
        if kind == "face":
            extras = "jsonb_build_object('embeddings', COALESCE((SELECT jsonb_agg(to_jsonb(e) - 'version' ORDER BY e.model_id) FROM pg_demo_face_embedding_history e WHERE e.face_id=h.id AND e.version=h.version), '[]'::jsonb))"
        entity = (
            "h.id"
            if kind == "entity"
            else "h.entity_id"
            if kind in ("face", "mention")
            else "NULL::uuid"
        )
        source = (
            "h.id"
            if kind == "source"
            else "h.source_id"
            if kind in ("face", "mention")
            else "NULL::uuid"
        )
        op.execute(
            f"INSERT INTO pg_demo_object_history SELECT '{kind}', h.id, h.version, h.change_id, h.deleted, {entity}, {source}, (to_jsonb(h) - 'change_id' - 'deleted') || {extras} FROM pg_demo_{table}_history h"
        )
    for table in (
        "face_embedding",
        "alias",
        "source",
        "text_mention",
        "face",
        "entity",
    ):
        op.drop_table("pg_demo_" + table + "_history")
