from fastapi import APIRouter

from people_gator_api.routes.v1.annotations import router as annotations_router
from people_gator_api.routes.v1.identities import router as identities_router
from people_gator_api.routes.v1.principals import router as principals_router
from people_gator_api.routes.v1.root import router as root_router
from people_gator_api.routes.v1.search import router as search_router
from people_gator_api.routes.v1.search_profiles import router as search_profiles_router
from people_gator_api.routes.v1.sources import router as sources_router

router = APIRouter(prefix="/api/v1")
router.include_router(search_profiles_router)
router.include_router(search_router)
router.include_router(identities_router)
router.include_router(annotations_router)
router.include_router(sources_router)
router.include_router(principals_router)
router.include_router(root_router)

__all__ = ["router"]
