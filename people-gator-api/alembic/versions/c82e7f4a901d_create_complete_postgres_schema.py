"""Create the complete PostgreSQL schema after the extension-only revisions.

This is a frozen schema snapshot. Existing databases bootstrapped with create_all
must pass the schema-only check before an operator stamps this revision.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector.sqlalchemy.vector

revision = "c82e7f4a901d"
down_revision = "65c4e6cdfa7f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Frozen table and static-index definitions.
    op.create_table('pg_demo_face_models',
    sa.Column('stub', sa.String(length=255), nullable=False),
    sa.Column('embedding_dim', sa.Integer(), nullable=False),
    sa.CheckConstraint('embedding_dim > 0', name='ck_pg_demo_face_model_embedding_dim'),
    sa.PrimaryKeyConstraint('stub')
    )
    op.create_table('pg_demo_sources',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('source_type', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('url')
    )
    op.create_index(op.f('ix_pg_demo_sources_source_type'), 'pg_demo_sources', ['source_type'], unique=False)
    op.create_table('pg_demo_users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('display_name', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('external_subject', sa.Text(), nullable=False),
    sa.Column('external_issuer', sa.Text(), nullable=False),
    sa.Column('email', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('external_issuer', 'external_subject', name='uq_pg_demo_user_external_identity')
    )
    op.create_index(op.f('ix_pg_demo_users_is_active'), 'pg_demo_users', ['is_active'], unique=False)
    op.create_table('pg_demo_documents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('library', sa.String(length=255), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['pg_demo_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('library', 'document_id', name='uq_pg_demo_document_identity')
    )
    op.create_table('pg_demo_entities',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=64), nullable=True),
    sa.Column('name', sa.Text(), nullable=True),
    sa.Column('name_normalized', sa.Text(), sa.Computed('lower(demo_unaccent(name))', persisted=True), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('short_description', sa.Text(), nullable=True),
    sa.Column('wikidata_id', sa.String(length=64), nullable=True),
    sa.Column('nlcr_authority_id', sa.String(length=128), nullable=True),
    sa.Column('search_document', postgresql.TSVECTOR(), sa.Computed("to_tsvector('simple'::regconfig,\n            coalesce(name, '') || ' ' || coalesce(description, '') || ' ' ||\n            coalesce(short_description, ''))", persisted=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['pg_demo_users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pg_demo_entities_kind'), 'pg_demo_entities', ['kind'], unique=False)
    op.create_index('ix_pg_demo_entities_name_trgm', 'pg_demo_entities', ['name_normalized'], unique=False, postgresql_using='gin', postgresql_ops={'name_normalized': 'gin_trgm_ops'})
    op.create_index(op.f('ix_pg_demo_entities_nlcr_authority_id'), 'pg_demo_entities', ['nlcr_authority_id'], unique=False)
    op.create_index('ix_pg_demo_entities_search', 'pg_demo_entities', ['search_document'], unique=False, postgresql_using='gin')
    op.create_index(op.f('ix_pg_demo_entities_user_id'), 'pg_demo_entities', ['user_id'], unique=False)
    op.create_index(op.f('ix_pg_demo_entities_wikidata_id'), 'pg_demo_entities', ['wikidata_id'], unique=False)
    op.create_table('pg_demo_images',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['pg_demo_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('pg_demo_pages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('library', sa.String(length=255), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('page_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['id'], ['pg_demo_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('library', 'document_id', 'page_id', name='uq_pg_demo_page_identity')
    )
    op.create_index('ix_pg_demo_page_document', 'pg_demo_pages', ['library', 'document_id'], unique=False)
    op.create_table('pg_demo_aliases',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('name_normalized', sa.Text(), sa.Computed('lower(demo_unaccent(name))', persisted=True), nullable=False),
    sa.Column('search_document', postgresql.TSVECTOR(), sa.Computed("to_tsvector('simple'::regconfig, name)", persisted=True), nullable=False),
    sa.ForeignKeyConstraint(['entity_id'], ['pg_demo_entities.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('entity_id', 'name', name='uq_pg_demo_alias_entity_name')
    )
    op.create_index(op.f('ix_pg_demo_aliases_entity_id'), 'pg_demo_aliases', ['entity_id'], unique=False)
    op.create_index('ix_pg_demo_aliases_name_trgm', 'pg_demo_aliases', ['name_normalized'], unique=False, postgresql_using='gin', postgresql_ops={'name_normalized': 'gin_trgm_ops'})
    op.create_index('ix_pg_demo_aliases_search', 'pg_demo_aliases', ['search_document'], unique=False, postgresql_using='gin')
    op.create_table('pg_demo_image_occurrences',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('source_id', sa.UUID(), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=True),
    sa.Column('occurrence_type', sa.String(length=32), nullable=False),
    sa.Column('roi', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['entity_id'], ['pg_demo_entities.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['source_id'], ['pg_demo_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pg_demo_image_occurrences_entity_id'), 'pg_demo_image_occurrences', ['entity_id'], unique=False)
    op.create_index(op.f('ix_pg_demo_image_occurrences_occurrence_type'), 'pg_demo_image_occurrences', ['occurrence_type'], unique=False)
    op.create_index(op.f('ix_pg_demo_image_occurrences_source_id'), 'pg_demo_image_occurrences', ['source_id'], unique=False)
    op.create_table('pg_demo_text_mentions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('source_id', sa.UUID(), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=True),
    sa.Column('mention', sa.Text(), nullable=False),
    sa.Column('mention_normalized', sa.Text(), sa.Computed('lower(demo_unaccent(mention))', persisted=True), nullable=False),
    sa.Column('context', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['entity_id'], ['pg_demo_entities.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['source_id'], ['pg_demo_sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pg_demo_text_mentions_entity_id'), 'pg_demo_text_mentions', ['entity_id'], unique=False)
    op.create_index('ix_pg_demo_text_mentions_mention_trgm', 'pg_demo_text_mentions', ['mention_normalized'], unique=False, postgresql_using='gin', postgresql_ops={'mention_normalized': 'gin_trgm_ops'})
    op.create_index(op.f('ix_pg_demo_text_mentions_source_id'), 'pg_demo_text_mentions', ['source_id'], unique=False)
    op.create_table('pg_demo_faces',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('identifier', sa.Text(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('keypoints', sa.ARRAY(sa.Float(), dimensions=2), nullable=False),
    sa.Column('keypoint_types', sa.ARRAY(sa.String()), nullable=False),
    sa.CheckConstraint('array_ndims(keypoints) = 2\n            AND array_length(keypoints, 1) = 5\n            AND array_length(keypoints, 2) = 2', name='ck_pg_demo_face_five_2d_keypoints'),
    sa.CheckConstraint('cardinality(keypoint_types) = 5', name='ck_pg_demo_face_five_keypoint_types'),
    sa.ForeignKeyConstraint(['id'], ['pg_demo_image_occurrences.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['pg_demo_users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pg_demo_faces_user_id'), 'pg_demo_faces', ['user_id'], unique=False)
    op.create_table('pg_demo_face_embeddings',
    sa.Column('face_id', sa.UUID(), nullable=False),
    sa.Column('model_id', sa.String(length=255), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(), nullable=False),
    sa.CheckConstraint('vector_dims(embedding) > 0', name='ck_pg_demo_face_embedding_nonempty'),
    sa.ForeignKeyConstraint(['face_id'], ['pg_demo_faces.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['model_id'], ['pg_demo_face_models.stub'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('face_id', 'model_id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
# ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('pg_demo_face_embeddings')
    op.drop_table('pg_demo_faces')
    op.drop_table('pg_demo_text_mentions')
    op.drop_table('pg_demo_image_occurrences')
    op.drop_table('pg_demo_aliases')
    op.drop_table('pg_demo_pages')
    op.drop_table('pg_demo_images')
    op.drop_table('pg_demo_entities')
    op.drop_table('pg_demo_documents')
    op.drop_table('pg_demo_users')
    op.drop_table('pg_demo_sources')
    op.drop_table('pg_demo_face_models')
    # ### end Alembic commands ###
