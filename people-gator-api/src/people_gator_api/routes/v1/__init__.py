from fastapi import APIRouter

from people_gator_api.routes.v1.annotations import router as annotations_router
from people_gator_api.routes.v1.entities import router as identities_router
from people_gator_api.routes.v1.face_models import router as face_models_router
from people_gator_api.routes.v1.media import router as media_router
from people_gator_api.routes.v1.users import router as users_router
from people_gator_api.routes.v1.root import router as root_router
from people_gator_api.routes.v1.rum_config import router as rum_config_router
from people_gator_api.routes.v1.search import router as search_router
from people_gator_api.routes.v1.sources import router as sources_router
from people_gator_api.routes.v1.text_mentions import (
    router as text_mentions_router,
)
from people_gator_api.routes.v1.translation import router as translation_router

router = APIRouter(prefix="/api/v1")
router.include_router(search_router)
router.include_router(identities_router)
router.include_router(annotations_router)
router.include_router(face_models_router)
router.include_router(text_mentions_router)
router.include_router(sources_router)
router.include_router(media_router)
router.include_router(users_router)
from people_gator_api.routes.v1.api_keys import router as api_keys_router
router.include_router(api_keys_router)
router.include_router(translation_router)
router.include_router(root_router)
router.include_router(rum_config_router)

__all__ = ["router"]
