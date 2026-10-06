from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.persistence.contracts import (
    FaceModelRepository,
)
from people_gator_api.schemas.face_models import (
    FaceModelListResponse,
    FaceModelRegisterRequest,
    FaceModelResponse,
)
from sqlalchemy import select
from people_gator_api.persistence.postgres.models import (
    FaceModel,
    face_embedding_hnsw_index,
)

from people_gator_api.persistence.postgres.utils import (
    face_model_response,
)
class PostgresFaceModelRepository(FaceModelRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def register(self, payload: FaceModelRegisterRequest) -> FaceModelResponse:
        model = await self._session.get(FaceModel, payload.model_stub)
        if model is None:
            model = FaceModel(
                stub=payload.model_stub,
                embedding_dim=payload.embedding_dim,
            )
            self._session.add(model)
            try:
                await self._session.flush()
            except IntegrityError as exc:
                await self._session.rollback()
                model = await self._session.get(FaceModel, payload.model_stub)
                if model is None:
                    raise ValueError("face model registration conflict") from exc
                if model.embedding_dim != payload.embedding_dim:
                    message = f"face model '{payload.model_stub}' is already "
                    message += f"registered with dimension {model.embedding_dim}"
                    raise ValueError(message) from exc
        elif model.embedding_dim != payload.embedding_dim:
            message = f"face model '{payload.model_stub}' is already registered with "
            message += f"dimension {model.embedding_dim}"
            raise ValueError(message)

        index = face_embedding_hnsw_index(model.stub, model.embedding_dim)
        try:
            connection = await self._session.connection()
            await connection.run_sync(
                lambda sync_connection: index.create(
                    sync_connection,
                    checkfirst=True,
                )
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return face_model_response(model)

    async def list(self) -> FaceModelListResponse:
        models = await self._session.scalars(select(FaceModel).order_by(FaceModel.stub))
        return FaceModelListResponse(
            items=[face_model_response(model) for model in models]
        )
