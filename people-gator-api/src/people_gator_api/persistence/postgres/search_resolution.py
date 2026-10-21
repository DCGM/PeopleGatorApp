"""Resolve entity references inside the search repository, before candidate retrieval."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.schemas.missing import MISSING, missing_to_none
from people_gator_api.schemas.search import SearchEntitiesRequest, SearchFacesRequest

from .models import Alias, Entity, Face, FaceEmbedding
from .utils import reference_vectors, usable_cosine_vector


async def resolve_entity_search[T: SearchEntitiesRequest | SearchFacesRequest](
    session: AsyncSession,
    request: T,
) -> T:
    query = request.query
    if query.entity_id is None:
        return request
    entity = await session.get(Entity, query.entity_id)
    if entity is None:
        raise ValueError(f"reference entity does not exist: {query.entity_id}")

    # Explicit IDs retain strict validation even when derived inputs are usable.
    face_ids = list(missing_to_none(query.face_id) or [])
    if face_ids:
        await reference_vectors(session, face_ids, query.face_embedding_model)
    terms = list(missing_to_none(query.text) or [])
    if "name" in query.entity_annotations and entity.name and entity.name.strip():
        terms.append(entity.name)
    if "aliases" in query.entity_annotations:
        aliases = await session.scalars(
            select(Alias.name).where(Alias.entity_id == entity.id).order_by(Alias.id)
        )
        terms.extend(value for value in aliases if value.strip())
    if "faces" in query.entity_annotations:
        # Resolve the complete compatible set, not a paginated face list. Missing
        # models/zero vectors are absent signals, not malformed explicit inputs.
        rows = await session.execute(
            select(Face.id, FaceEmbedding.embedding)
            .join(FaceEmbedding, FaceEmbedding.face_id == Face.id)
            .where(
                Face.entity_id == entity.id,
                FaceEmbedding.model_id == query.face_embedding_model,
            )
            .order_by(Face.id)
        )
        face_ids.extend(
            face_id for face_id, vector in rows if usable_cosine_vector(list(vector))
        )
    terms = list(dict.fromkeys(terms))
    face_ids = list(dict.fromkeys(face_ids))
    if not terms and not face_ids:
        raise ValueError(
            "selected entity annotations provide no usable search signal; choose name, aliases, another face model or supply explicit inputs"
        )
    return request.model_copy(
        update={
            "query": query.model_copy(
                update={
                    "text": terms or MISSING,
                    "face_id": face_ids or MISSING,
                }
            )
        }
    )
