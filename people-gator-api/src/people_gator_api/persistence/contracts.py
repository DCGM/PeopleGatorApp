"""Backend-neutral persistence behavior for PostgreSQL and Weaviate.

Repository methods are asynchronous and operate on API schemas only. Ordinary
list results are ordered by object UUID ascending; search results are ordered by
score descending and UUID ascending. Cursors are opaque backend-defined strings
and exclusive. An unknown cursor or a cursor produced by different query inputs
is invalid.

Filter fields are combined with logical AND and values inside a filter list with
logical OR. Empty filter lists are invalid. When requested, total_count counts
all matching records before cursor and limit.

For page filters, ``has_mentions`` and ``has_faces`` test for the existence of
at least one text mention or face detection, whether assigned to an entity or
not. ``has_entities`` tests for at least one text mention or face detection
that is assigned to an entity. A true value requires that presence and a false
value requires its absence. These filters are combined with each other and all
other supplied fields using logical AND.

Successful batch results preserve input order. Patch batches require unique
object IDs; duplicate IDs are invalid. Delete batches de-duplicate IDs and count
each stored object once. Empty batches succeed with an empty result or zero.
Batches are not guaranteed to be atomic: an error is raised, but a backend that
cannot roll back may retain earlier successful writes.

References named by create or patch payloads must already exist. Missing
references are errors. Deleting an entity unassigns its faces and text mentions;
merging an entity reassigns its faces and text mentions to the target, copies
unique aliases to the target, and deletes the source atomically, leaving the
target's other fields unchanged;
deleting a source cascades its faces and text mentions; deleting a referenced
user is rejected. Invalid cursors and duplicate patch IDs raise ValueError.
"""

from __future__ import annotations

import enum
import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pydantic import AnyUrl
from people_gator_api.schemas.common import GenericActor, GenericListRequest
from people_gator_api.schemas.api_keys import APIKeyCreateRequest, APIKeyResponse, APIKeyListResponse
from people_gator_api.schemas.missing import MISSING, MissingType
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityDeleteManyRequest,
    EntityDeleteManyResponse,
    EntityListFilter,
    EntityListRequest,
    EntityListResponse,
    EntityMergeResponse,
    EntityMergeBatchResponse,
    EntityMergeTargetPatch,
    EntityPatchRequest,
    EntityPatchBatchItem,
    EntityResponse,
)
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.faces import (
    FaceCreateRequest,
    FaceListRequest,
    FaceListResponse,
    FacePatchBatchItem,
    FacePatchRequest,
    FaceResponse,
)
from people_gator_api.schemas.face_models import (
    FaceModelListResponse,
    FaceModelRegisterRequest,
    FaceModelResponse,
)
from people_gator_api.schemas.search import (
    SearchDocumentsRequest,
    SearchDocumentsResultListResponse,
    SearchEntitiesRequest,
    SearchEntitiesResultListResponse,
    SearchFacesRequest,
    SearchFacesResultListResponse,
    SearchPagesRequest,
    SearchPagesResultListResponse,
)
from people_gator_api.schemas.sources import (
    DocumentCreateRequest,
    DocumentListRequest,
    DocumentListResponse,
    DocumentLookupRequest,
    DocumentResponse,
    GenericSourceCreateRequest,
    GenericSourceListRequest,
    GenericSourceListResponse,
    GenericSourceLookupRequest,
    GenericSourceResponse,
    ImageCreateRequest,
    ImageLookupRequest,
    ImageListRequest,
    ImageListResponse,
    ImageResponse,
    PageCreateRequest,
    PageListRequest,
    PageListResponse,
    PageLookupRequest,
    PageResponse,
    SourceCreateRequestBase,
    SourceListRequest,
    SourceListResponse,
    SourceResponseBase,
    to_document_list_response,
    to_generic_list_request,
    to_image_list_response,
    to_page_list_response,
    to_source_list_response,
)
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionPatchRequest,
    TextMentionPatchBatchItem,
    TextMentionListRequest,
    TextMentionListResponse,
    TextMentionResponse,
)
from people_gator_api.schemas.users import (
    UserCreateRequest,
    UserListRequest,
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)


class CreateResult(enum.StrEnum):
    EXISTING = "existing"
    CREATED = "created"


class EntityRepository(ABC):
    @abstractmethod
    async def get(self, entity_id: uuid.UUID) -> EntityResponse | None:
        """
        Retrieve an entity by its unique identifier.

        :param self: The instance of the repository.
        :param entity_id: The unique identifier of the entity to retrieve.
        :type entity_id: uuid.UUID
        :return: The entity corresponding to the given ID, or None if not found.
        :rtype: EntityResponse | None
        """

    @abstractmethod
    async def list(self, query: EntityListRequest) -> EntityListResponse:
        """
        Retrieve a list of entities based on the given query.

        :param self: The instance of the repository.
        :param query: The query parameters for listing entities.
        :type query: EntityListRequest
        :return: A list of entities matching the query.
        :rtype: EntityListResponse
        """

    @abstractmethod
    async def create(
        self, payload: EntityCreateRequest, context: GenericActor
    ) -> EntityResponse:
        """
        Create a new entity with the given payload and context.

        :param self: The instance of the repository.
        :param payload: The data for the entity to be created.
        :type payload: EntityCreateRequest
        :param context: The context of the actor performing the creation.
        :type context: GenericActor
        :return: The created entity.
        :rtype: EntityResponse
        """

    @abstractmethod
    async def create_batch(
        self, payloads: Sequence[EntityCreateRequest], context: GenericActor
    ) -> list[EntityResponse]:
        """
        Create a batch of entities with the given payloads and context.

        :param self: The instance of the repository.
        :param payloads: The list of entity data to be created.
        :type payloads: Sequence[EntityCreateRequest]
        :param context: The context of the actor performing the creation.
        :type context: GenericActor
        :return: The list of created entities.
        :rtype: list[EntityResponse]
        """

    @abstractmethod
    async def patch(
        self, entity_id: uuid.UUID, payload: EntityPatchRequest, context: GenericActor
    ) -> EntityResponse | None:
        """
        Patch an existing entity with the given payload and context.

        Always the actor performing the patch must be specified through the context.

        Ideally, should persist information about actor performing the patch.

        :param self: The instance of the repository.
        :param entity_id: The unique identifier of the entity to patch.
        :type entity_id: uuid.UUID
        :param payload: The patch data for the entity.
        :type payload: EntityPatchRequest
        :param context: The context of the actor performing the patch.
        :type context: GenericActor
        :return: The updated entity, or None if the entity does not exist.
        :rtype: EntityResponse | None
        """

    @abstractmethod
    async def patch_batch(
        self, commands: Sequence[EntityPatchBatchItem], context: GenericActor
    ) -> list[EntityResponse | None]:
        """
        Patch a batch of entities with the given commands.

        :param self: The instance of the repository.
        :param commands: The list of patch commands for the entities.
        :type commands: Sequence[EntityPatchBatchItem]
        :param context: The context of the actor performing the batch patch.
        :type context: GenericActor
        :return: The list of updated entities, with None for entities that do not exist.
        :rtype: list[EntityResponse | None]
        """

    @abstractmethod
    async def delete(self, entity_id: uuid.UUID) -> bool:
        """Delete an entity and unassign its faces and text mentions.

        Return False when the entity does not exist.
        """

    async def merge(
        self,
        target_entity_id: uuid.UUID,
        source_entity_id: uuid.UUID,
        target_patch: EntityMergeTargetPatch | None = None,
    ) -> EntityMergeResponse | None:
        """Merge one source into the target using the batch operation."""
        result = await self.merge_batch(
            target_entity_id, [source_entity_id], target_patch=target_patch
        )
        if result is None:
            return None
        return EntityMergeResponse(
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            faces_reassigned=result.faces_reassigned,
            text_mentions_reassigned=result.text_mentions_reassigned,
            merged_entity=result.merged_entity,
        )

    @abstractmethod
    async def merge_batch(
        self,
        target_entity_id: uuid.UUID,
        source_entity_ids: Sequence[uuid.UUID],
        target_patch: EntityMergeTargetPatch | None = None,
    ) -> EntityMergeBatchResponse | None:
        """Atomically merge all sources into the target and delete the sources.

        Source aliases absent from the target are added to it. Explicit description
        and short description values update the target; null clears them, while
        omitted values preserve them. Other fields are preserved. Return None if the target or any
        source is missing. Source IDs must be nonempty, unique, and distinct from the
        target ID; invalid IDs raise ValueError.
        """

    async def delete_batch(
        self, entity_ids: Sequence[uuid.UUID]
    ) -> EntityDeleteManyResponse:
        unique_ids = list(dict.fromkeys(entity_ids))
        if not unique_ids:
            return EntityDeleteManyResponse(deleted_count=0)
        request = EntityDeleteManyRequest(
            filter=EntityListFilter(entity_id=unique_ids),
            limit=len(unique_ids),
        )
        return await self.delete_many(request)

    @abstractmethod
    async def delete_many(
        self, selector: EntityDeleteManyRequest
    ) -> EntityDeleteManyResponse:
        """
        Delete multiple entities based on the given selector.

        Same relationship delete behaviour as single item delete.

        :param self: The instance of the repository.
        :param selector: The request containing the filter and limit for deletion.
        :type selector: EntityDeleteManyRequest, containing optionally filter. If no filter is provided, all entities up to the specified limit will be deleted.
        :return: The response containing the result of the deletion operation. Mainly number of successfully deleted entities.
        :rtype: EntityDeleteManyResponse
        """

    @abstractmethod
    async def search(
        self, query: SearchEntitiesRequest
    ) -> SearchEntitiesResultListResponse:
        """
        Search for entities based on the given query.

        Take the configuraiton from the query object.
        Vector-searchable items will be handled according to the vector search configuration specified in the query object.
        Fusion of muliple scores given by different search fields will be performed according to the configuration specified in the query object.

        The final ranking of entities will be based on the fused scores.

        For filters, the logical operations are applied as follows:
        Logical OR will be applied on list of items within each filter field.
        Logical AND is applied between different filter fields.

        :param self: The instance of the repository.
        :param query: The search query containing filters, pagination, and other search parameters.
        :type query: SearchEntitiesRequest
        :return: The list of entities matching the search criteria.
        :rtype: SearchEntitiesResultListResponse
        """


class SourceRepository(ABC):
    """Sources are globally URL-unique and have immutable type-specific identities.

    Page identity is (library, document_id, page_id), document identity is
    (library, document_id), and image identity is its normalized URL. A conflicting
    URL or identity is an error; changes are delete-and-reinsert operations.
    """

    @abstractmethod
    async def lookup(
        self, lookup: GenericSourceLookupRequest
    ) -> GenericSourceResponse | None:
        """
        Retrieve a generic source based on the lookup request.

        Should implement depolymorphic retrieval independent of the source type.
        It has GenericSourceResponse as response which flattens all polymorphic source types.

        :param self: The instance of the repository.
        :param lookup: The request containing the source type and identifiers.
        :type lookup: GenericSourceLookupRequest
        :return: The response containing the source information, or None if not found.
        :rtype: GenericSourceResponse | None
        """

    async def _lookup[T: SourceResponseBase](
        self,
        cls: type[T],
        source_id: uuid.UUID | MissingType = MISSING,
        source_type: SourceKind | MissingType = MISSING,
        url: AnyUrl | MissingType = MISSING,
        library: str | MissingType = MISSING,
        document_id: uuid.UUID | MissingType = MISSING,
        page_id: uuid.UUID | MissingType = MISSING,
    ) -> T | None:
        """Look up and convert a source, returning None for a type mismatch."""
        response = await self.lookup(
            GenericSourceLookupRequest(
                source_type=source_type,
                source_id=source_id,
                url=url,
                library=library,
                document_id=document_id,
                page_id=page_id,
            )
        )
        if response is None:
            return None
        response_to_source_kind: dict[type[SourceResponseBase], SourceKind] = {
            PageResponse: SourceKind.page,
            DocumentResponse: SourceKind.document,
            ImageResponse: SourceKind.image,
        }
        expected_type = response_to_source_kind.get(cls)
        if expected_type is not None and response.source_type != expected_type:
            return None
        return cls.from_generic(response)

    async def get_page(self, source_id: uuid.UUID) -> PageResponse | None:
        """
        Retrieve a page source based on the source ID.

        :param self: The instance of the repository.
        :param source_id: The unique identifier of the page source.
        :type source_id: uuid.UUID
        :return: The response containing the page information, or None if not found.
        :rtype: PageResponse | None
        """
        return await self._lookup(source_id=source_id, cls=PageResponse)

    async def get_document(self, source_id: uuid.UUID) -> DocumentResponse | None:
        """
        Retrieve a document source based on the source ID.

        :param self: The instance of the repository.
        :param source_id: The unique identifier of the document source.
        :type source_id: uuid.UUID
        :return: The response containing the document information, or None if not found.
        :rtype: DocumentResponse | None
        """
        return await self._lookup(source_id=source_id, cls=DocumentResponse)

    async def get_image(self, source_id: uuid.UUID) -> ImageResponse | None:
        """
        Retrieve an image source based on the source ID.

        :param self: The instance of the repository.
        :param source_id: The unique identifier of the image source.
        :type source_id: uuid.UUID
        :return: The response containing the image information, or None if not found.
        :rtype: ImageResponse | None
        """
        return await self._lookup(source_id=source_id, cls=ImageResponse)

    async def get_source(self, source_id: uuid.UUID) -> SourceResponseBase | None:
        """
        Retrieve a generic source based on the source ID.

        :param self: The instance of the repository.
        :param source_id: The unique identifier of the source.
        :type source_id: uuid.UUID
        :return: The response containing the source information, or None if not found.
        :rtype: SourceResponseBase | None
        """
        return await self._lookup(
            source_id=source_id, source_type=MISSING, cls=SourceResponseBase
        )

    async def lookup_page(self, lookup: PageLookupRequest) -> PageResponse | None:
        """
        Retrieve a page source based on the lookup request.

        :param self: The instance of the repository.
        :param lookup: The lookup request containing the library, document ID, and page ID.
        :type lookup: PageLookupRequest
        :return: The response containing the page information, or None if not found.
        :rtype: PageResponse | None
        """
        return await self._lookup(
            cls=PageResponse,
            source_type=SourceKind.page,
            library=lookup.library,
            document_id=lookup.document_id,
            page_id=lookup.page_id,
        )

    async def lookup_document(
        self, lookup: DocumentLookupRequest
    ) -> DocumentResponse | None:
        """
        Retrieve a document source based on the lookup request.

        :param self: The instance of the repository.
        :param lookup: The lookup request containing the library and document ID.
        :type lookup: DocumentLookupRequest
        :return: The response containing the document information, or None if not found.
        :rtype: DocumentResponse | None
        """
        return await self._lookup(
            cls=DocumentResponse,
            source_type=SourceKind.document,
            library=lookup.library,
            document_id=lookup.document_id,
        )

    async def lookup_image(self, lookup: ImageLookupRequest) -> ImageResponse | None:
        """
        Retrieve an image source based on the lookup request.

        :param self: The instance of the repository.
        :param lookup: The lookup request containing the URL of the image.
        :type lookup: ImageLookupRequest
        :return: The response containing the image information, or None if not found.
        :rtype: ImageResponse | None
        """
        return await self._lookup(
            cls=ImageResponse,
            source_type=SourceKind.image,
            url=lookup.url,
        )

    @abstractmethod
    async def list(self, query: GenericSourceListRequest) -> GenericSourceListResponse:
        """
        Retrieve a list of sources based on the query.

        Should return a paginated list of sources matching the query criteria.
        The criteria is flatted version of all subclasses of sources' listing criteria.
        The response should include the sources that match the flattened criteria.
        The sources have to be also in the generic source with all relevant fields populated.
        This method is idelly "dumb" it does not ideally know about types of sources it is listing.

        Query contains filters that are applied as follows:
        - Results matching fields within single rield list are joined by Logical OR.
        - Results matching fields across different field lists are joined by Logical AND.

        :param self: The instance of the repository.
        :param query: The query request containing the filtering and pagination information.
        :type query: GenericSourceListRequest
        :return: The response containing the list of sources.
        :rtype: GenericSourceListResponse
        """

    async def list_pages(self, query: PageListRequest) -> PageListResponse:
        """
        Retrieve a paginated list of pages based on the query.

        :param self: The instance of the repository.
        :param query: The query request containing the filtering and pagination information.
        :type query: PageListRequest
        :return: The response containing the list of pages.
        :rtype: PageListResponse
        """
        generic_list = await self.list(to_generic_list_request(query))
        return to_page_list_response(generic_list)

    async def list_documents(self, query: DocumentListRequest) -> DocumentListResponse:
        """
        Retrieve a paginated list of documents based on the query.

        :param self: The instance of the repository.
        :param query: The query request containing the filtering and pagination information.
        :type query: DocumentListRequest
        :return: The response containing the list of documents.
        :rtype: DocumentListResponse
        """
        generic_list = await self.list(to_generic_list_request(query))
        return to_document_list_response(generic_list)

    async def list_images(self, query: ImageListRequest) -> ImageListResponse:
        """
        Retrieve a paginated list of images based on the query.

        :param self: The instance of the repository.
        :param query: The query request containing the filtering and pagination information.
        :type query: ImageListRequest
        :return: The response containing the list of images.
        :rtype: ImageListResponse
        """
        generic_list = await self.list(to_generic_list_request(query))
        return to_image_list_response(generic_list)

    async def list_sources(self, query: SourceListRequest) -> SourceListResponse:
        """
        Retrieve a paginated list of sources based on the query.

        :param self: The instance of the repository.
        :param query: The query request containing the filtering and pagination information.
        :type query: SourceListRequest
        :return: The response containing the list of sources.
        :rtype: SourceListResponse
        """
        generic_list = await self.list(to_generic_list_request(query))
        return to_source_list_response(generic_list)

    @abstractmethod
    async def get_or_create(
        self, spec: GenericSourceCreateRequest
    ) -> tuple[GenericSourceResponse, CreateResult]:
        """
        Retrieve an existing generic source matching the specification or create a new one if it doesn't exist.

        :param self: The instance of the repository.
        :param spec: The specification for the generic source to retrieve or create.
        :type spec: GenericSourceCreateRequest
        :return: A tuple containing the response for the generic source and a flag indicating if it was created.
        :rtype: tuple[GenericSourceResponse, CreateResult]
        """

    async def get_or_create_page(
        self, spec: PageCreateRequest
    ) -> tuple[PageResponse, CreateResult]:
        """
        Retrieve an existing page matching the specification or create a new one if it doesn't exist.

        :param self: The instance of the repository.
        :param spec: The specification for the page to retrieve or create.
        :type spec: PageCreateRequest
        :return: A tuple containing the response for the page and a flag indicating if it was created.
        :rtype: tuple[PageResponse, CreateResult]
        """
        generic_response, created = await self.get_or_create(spec.to_generic())
        return PageResponse.from_generic(generic_response), created

    async def get_or_create_document(
        self, spec: DocumentCreateRequest
    ) -> tuple[DocumentResponse, CreateResult]:
        """
        Retrieve an existing document matching the specification or create a new one if it doesn't exist.

        :param self: The instance of the repository.
        :param spec: The specification for the document to retrieve or create.
        :type spec: DocumentCreateRequest
        :return: A tuple containing the response for the document and a flag indicating if it was created.
        :rtype: tuple[DocumentResponse, CreateResult]
        """
        generic_response, created = await self.get_or_create(spec.to_generic())
        return DocumentResponse.from_generic(generic_response), created

    async def get_or_create_image(
        self, spec: ImageCreateRequest
    ) -> tuple[ImageResponse, CreateResult]:
        """
        Retrieve an existing image matching the specification or create a new one if it doesn't exist.

        :param self: The instance of the repository.
        :param spec: The specification for the image to retrieve or create.
        :type spec: ImageCreateRequest
        :return: A tuple containing the response for the image and a flag indicating if it was created.
        :rtype: tuple[ImageResponse, CreateResult]
        """
        generic_response, created = await self.get_or_create(spec.to_generic())
        return ImageResponse.from_generic(generic_response), created

    @abstractmethod
    async def get_or_create_batch(
        self, specs: Sequence[GenericSourceCreateRequest]
    ) -> list[tuple[GenericSourceResponse, CreateResult]]:
        """
        Retrieve existing generic sources matching the specifications or create new ones if they don't exist.

        Only unique new items are inserted into the repository.
        Repeated input identities are returned from the repository. The first new occurrence is CREATED and later occurrences are EXISTING.
        The order of the returned results corresponds to the order of the input specifications.

        :param self: The instance of the repository.
        :param specs: The specifications for the generic sources to retrieve or create.
        :type specs: Sequence[GenericSourceCreateRequest]
        :return: A list of tuples containing the responses for the generic sources and flags indicating if they were created.
        :rtype: list[tuple[GenericSourceResponse, CreateResult]]
        """

    async def _get_or_create_batch[TO: SourceResponseBase, TI: SourceCreateRequestBase](
        self,
        specs: Sequence[TI],
        cls: type[TO],
    ) -> list[tuple[TO, CreateResult]]:
        """
        Internal helper method to retrieve existing sources matching the specifications or create new ones if they don't exist.
        This method is intended for internal use within the repository and should not be called directly by external code.

        :param self: The instance of the repository.
        :param specs: The specifications for the sources to retrieve or create.
        :type specs: Sequence[TI]
        :param cls: The class type of the response objects.
        :type cls: type[TO]
        :return: A list of tuples containing the responses for the sources and flags indicating if they were created.
        :rtype: list[tuple[TO, CreateResult]]
        """

        generic_specs = [spec.to_generic() for spec in specs]
        generic_results = await self.get_or_create_batch(generic_specs)
        results = [
            (cls.from_generic(response), created)
            for response, created in generic_results
        ]
        return results

    async def get_or_create_image_batch(
        self, specs: Sequence[ImageCreateRequest]
    ) -> list[tuple[ImageResponse, CreateResult]]:
        """
        Retrieve existing images matching the specifications or create new ones if they don't exist.

        :param self: The instance of the repository.
        :param specs: The specifications for the images to retrieve or create.
        :type specs: Sequence[ImageCreateRequest]
        :return: A list of tuples containing the responses for the images and flags indicating if they were created.
        :rtype: list[tuple[ImageResponse, CreateResult]]
        """
        return await self._get_or_create_batch(
            specs=specs,
            cls=ImageResponse,
        )

    async def get_or_create_document_batch(
        self, specs: Sequence[DocumentCreateRequest]
    ) -> list[tuple[DocumentResponse, CreateResult]]:
        """
        Retrieve existing documents matching the specifications or create new ones if they don't exist.

        :param self: The instance of the repository.
        :param specs: The specifications for the documents to retrieve or create.
        :type specs: Sequence[DocumentCreateRequest]
        :return: A list of tuples containing the responses for the documents and flags indicating if they were created.
        :rtype: list[tuple[DocumentResponse, CreateResult]]
        """
        return await self._get_or_create_batch(
            specs=specs,
            cls=DocumentResponse,
        )

    async def get_or_create_page_batch(
        self, specs: Sequence[PageCreateRequest]
    ) -> list[tuple[PageResponse, CreateResult]]:
        """Get or create pages, preserving input order."""
        return await self._get_or_create_batch(
            specs=specs,
            cls=PageResponse,
        )

    @abstractmethod
    async def delete(self, source_id: uuid.UUID) -> bool:
        """Delete a source and cascade its dependent faces and mentions."""

    @abstractmethod
    async def delete_batch(self, source_ids: Sequence[uuid.UUID]) -> int:
        """Delete unique source IDs with the same cascade as delete().

        Duplicate IDs count once. Empty input returns zero.
        """

    @abstractmethod
    async def search_documents(
        self, query: SearchDocumentsRequest
    ) -> SearchDocumentsResultListResponse:
        """Search documents using the shared multimodal search semantics."""

    @abstractmethod
    async def search_pages(
        self, query: SearchPagesRequest
    ) -> SearchPagesResultListResponse:
        """
        Search for pages matching the given query.

        Take the configuration from the query object.
        Vector-searchable items will be handled according to the vector search configuration specified in the query object.
        Page-level per field aggregation will be performed according to the configuration specified in the query object.
        Page-level fusion of muliple scores given by different search fields will be performed according to the configuration specified in the query object.

        The final ranking of entities will be based on the fused scores.

        For filters, the logical operations are applied as follows:
        Logical OR will be applied on list of items within each filter field.
        Logical AND is applied between different filter fields.

        :param self: The instance of the repository.
        :param query: The search query for pages.
        :type query: SearchPagesRequest
        :return: The list of search results for the pages.
        :rtype: SearchPagesResultListResponse
        """


class FaceModelRepository(ABC):
    """Registry of face embedding models available to persistence."""

    @abstractmethod
    async def register(self, payload: FaceModelRegisterRequest) -> FaceModelResponse:
        """Register a stub/dimension pair and ensure its vector index exists.

        Re-registering the same pair is idempotent. Reusing a stub with another
        dimension is invalid.
        """

    @abstractmethod
    async def list(self) -> FaceModelListResponse:
        """List registered models ordered by stub."""


class FaceRepository(ABC):
    @abstractmethod
    async def get(self, detection_id: uuid.UUID) -> FaceResponse | None:
        """
        Retrieve a face by its detection ID.

        :param self: The instance of the repository.
        :param detection_id: The unique identifier of the face detection.
        :type detection_id: uuid.UUID
        :return: The response for the face if found, otherwise None.
        :rtype: FaceResponse | None
        """

    @abstractmethod
    async def list(self, query: FaceListRequest) -> FaceListResponse:
        """
        Retrieve a list of faces based on the given query.

        Query contains filter and is cursor based for pagination.

        Filter criteria for listing faces.
        - Logical OR will be applied on list of items within each filter field.
        - Logical AND is applied between different filter fields.

        :param self: The instance of the repository.
        :param query: The query parameters for listing faces.
        :type query: FaceListRequest
        :return: The list of faces matching the query.
        :rtype: FaceListResponse
        """

    @abstractmethod
    async def create(
        self, payload: FaceCreateRequest, context: GenericActor
    ) -> FaceResponse:
        """
        Create a new face entry based on the given payload and context.

        Optionally link to an existing entity.

        Must link to existing source.

        :param self: The instance of the repository.
        :param payload: The payload containing the face creation details.
        :type payload: FaceCreateRequest
        :param context: The context of the actor performing the operation.
        :type context: GenericActor
        :return: The response for the created face.
        :rtype: FaceResponse
        """

    @abstractmethod
    async def create_batch(
        self, payloads: Sequence[FaceCreateRequest], context: GenericActor
    ) -> list[FaceResponse]:
        """
        Create multiple new face entries based on the given payloads and context.

        Ideally in optimized batch operations to reduce overhead and improve performance.

        Same requirements as the single create operation apply here.

        :param self: The instance of the repository.
        :param payloads: The list of payloads containing the face creation details.
        :type payloads: Sequence[FaceCreateRequest]
        :param context: The context of the actor performing the operation.
        :type context: GenericActor
        :return: The list of responses for the created faces.
        :rtype: list[FaceResponse]
        """

    @abstractmethod
    async def patch(
        self,
        detection_id: uuid.UUID,
        payload: FacePatchRequest,
        context: GenericActor,
    ) -> FaceResponse | None:
        """Patch a face, returning None when the detection does not exist."""

    @abstractmethod
    async def patch_batch(
        self,
        commands: Sequence[FacePatchBatchItem],
        context: GenericActor,
    ) -> list[FaceResponse | None]:
        """Patch faces and preserve command order, using None for missing IDs."""

    @abstractmethod
    async def delete(self, detection_id: uuid.UUID) -> bool:
        """
        Delete an existing face entry based on the given detection ID.

        :param self: The instance of the repository.
        :param detection_id: The ID of the face detection to delete.
        :type detection_id: uuid.UUID
        :return: True if the face was successfully deleted, False otherwise.
        :rtype: bool
        """

    @abstractmethod
    async def delete_batch(self, detection_ids: Sequence[uuid.UUID]) -> int:
        """
        Delete multiple existing face entries based on the given detection IDs.

        Ideally more optimized than deleting each face individually.

        :param self: The instance of the repository.
        :param detection_ids: The list of face detection IDs to delete.
        :type detection_ids: Sequence[uuid.UUID]
        :return: The number of successfully deleted faces.
        :rtype: int
        """

    @abstractmethod
    async def search(self, query: SearchFacesRequest) -> SearchFacesResultListResponse:
        """
        Search for face entries based on the given query.

        :param self: The instance of the repository.
        :param query: The search query for faces.
        :type query: SearchFacesRequest
        :return: The list of search results for the faces.
        :rtype: SearchFacesResultListResponse
        """


class TextMentionRepository(ABC):
    @abstractmethod
    async def get(self, mention_id: uuid.UUID) -> TextMentionResponse | None:
        """
        Get an existing text mention entry based on the given mention ID.

        :param self: The instance of the repository.
        :param mention_id: The ID of the text mention to retrieve.
        :type mention_id: uuid.UUID
        :return: The response for the retrieved text mention, or None if not found.
        :rtype: TextMentionResponse | None
        """

    @abstractmethod
    async def list(self, query: TextMentionListRequest) -> TextMentionListResponse:
        """
        List text mention entries based on the given query.

        :param self: The instance of the repository.
        :param query: The query for listing text mentions.
        :type query: TextMentionListRequest
        :return: The list of text mentions matching the query.
        :rtype: TextMentionListResponse
        """

    @abstractmethod
    async def create(
        self, payload: TextMentionCreateRequest, context: GenericActor
    ) -> TextMentionResponse:
        """
        Create a new text mention entry based on the given payload.

        :param self: The instance of the repository.
        :param payload: The data for the text mention to create.
        :type payload: TextMentionCreateRequest
        :param context: The actor performing the creation.
        :type context: GenericActor
        :return: The response for the created text mention.
        :rtype: TextMentionResponse
        """

    @abstractmethod
    async def create_batch(
        self, payloads: Sequence[TextMentionCreateRequest], context: GenericActor
    ) -> list[TextMentionResponse]:
        """
        Create a batch of new text mention entries based on the given payloads.

        :param self: The instance of the repository.
        :param payloads: The data for the text mentions to create.
        :type payloads: Sequence[TextMentionCreateRequest]
        :param context: The actor performing the creation.
        :type context: GenericActor
        :return: The list of responses for the created text mentions.
        :rtype: list[TextMentionResponse]
        """

    @abstractmethod
    async def patch(
        self,
        mention_id: uuid.UUID,
        payload: TextMentionPatchRequest,
        context: GenericActor,
    ) -> TextMentionResponse | None:
        """
        Patch an existing text mention entry based on the given payload and context.

        :param self: The instance of the repository.
        :param mention_id: The ID of the text mention to patch.
        :type mention_id: uuid.UUID
        :param payload: The data for patching the text mention.
        :type payload: TextMentionPatchRequest
        :param context: The actor performing the patch.
        :type context: GenericActor
        :return: The response for the patched text mention, or None if not found.
        :rtype: TextMentionResponse | None
        """

    @abstractmethod
    async def patch_batch(
        self, commands: Sequence[TextMentionPatchBatchItem], context: GenericActor
    ) -> list[TextMentionResponse | None]:
        """
        Patch a batch of existing text mention entries based on the given commands.

        :param self: The instance of the repository.
        :param commands: The commands for patching the text mentions.
        :type commands: Sequence[TextMentionPatchBatchItem]
        :param context: The actor performing the patch.
        :type context: GenericActor
        :return: The list of responses for the patched text mentions, or None if not found.
        :rtype: list[TextMentionResponse | None]
        """

    @abstractmethod
    async def delete(self, mention_id: uuid.UUID) -> bool:
        """
        Delete an existing text mention entry by its ID.

        :param self: The instance of the repository.
        :param mention_id: The ID of the text mention to delete.
        :type mention_id: uuid.UUID
        :return: True if the text mention was deleted, False otherwise.
        :rtype: bool
        """

    @abstractmethod
    async def delete_batch(self, mention_ids: Sequence[uuid.UUID]) -> int:
        """
        Delete a batch of existing text mention entries by their IDs.

        :param self: The instance of the repository.
        :param mention_ids: The IDs of the text mentions to delete.
        :type mention_ids: Sequence[uuid.UUID]
        :return: The number of text mentions successfully deleted.
        :rtype: int
        """


class UserRepository(ABC):
    """Users are uniquely identified by (external_issuer, external_subject)."""

    @abstractmethod
    async def get(self, user_id: uuid.UUID) -> UserResponse | None:
        """
        Retrieve an existing user entry by its ID.

        :param self: The instance of the repository.
        :param user_id: The ID of the user to retrieve.
        :type user_id: uuid.UUID
        :return: The response for the retrieved user, or None if not found.
        :rtype: UserResponse | None
        """

    @abstractmethod
    async def list(self, query: UserListRequest) -> UserListResponse:
        """
        List existing user entries based on the given query.

        :param self: The instance of the repository.
        :param query: The query parameters for listing users.
        :type query: UserListRequest
        :return: The list of users matching the query.
        :rtype: UserListResponse
        """

    @abstractmethod
    async def get_or_create(self, payload: UserCreateRequest) -> UserResponse:
        """Get or create by (external_issuer, external_subject).

        If the identity already exists, return the stored record without
        applying the other create fields as an update.
        """

    @abstractmethod
    async def patch(
        self, user_id: uuid.UUID, payload: UserPatchRequest
    ) -> UserResponse | None:
        """
        Update an existing user entry by its ID.

        :param self: The instance of the repository.
        :param user_id: The ID of the user to update.
        :type user_id: uuid.UUID
        :param payload: The data for updating the user.
        :type payload: UserPatchRequest
        :return: The response for the updated user, or None if not found.
        :rtype: UserResponse | None
        """

    @abstractmethod
    async def delete(self, user_id: uuid.UUID) -> bool:
        """Delete an unreferenced user.

        Return False when the user does not exist. Raise ValueError when an
        entity or face still references the user.
        """

    @abstractmethod
    async def delete_batch(self, user_ids: Sequence[uuid.UUID]) -> int:
        """
        Delete multiple user entries by their IDs.

        :param self: The instance of the repository.
        :param user_ids: The IDs of the users to delete.
        :type user_ids: Sequence[uuid.UUID]
        :return: The number of users successfully deleted.
        :rtype: int
        """


class APIKeyRepository(ABC):
    @abstractmethod
    async def get_or_create(self, payload: APIKeyCreateRequest) -> APIKeyResponse:
        """Register a stable config identifier, returning the same ID under concurrency."""

    @abstractmethod
    async def list(self, query: GenericListRequest) -> APIKeyListResponse:
        """List registered identities, including keys removed from configuration."""


@dataclass(frozen=True, slots=True)
class Database:
    """One request-scoped, backend-neutral entry point."""

    entities: EntityRepository
    sources: SourceRepository
    faces: FaceRepository
    face_models: FaceModelRepository
    text_mentions: TextMentionRepository
    users: UserRepository
    api_keys: APIKeyRepository | None = None
