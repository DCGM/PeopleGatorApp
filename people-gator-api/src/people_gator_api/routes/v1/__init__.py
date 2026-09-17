from fastapi import APIRouter

from people_gator_api.routes.v1.annotations import router as annotations_router
from people_gator_api.routes.v1.entities import router as identities_router
from people_gator_api.routes.v1.media import router as media_router
from people_gator_api.routes.v1.page_layouts import router as page_layouts_router
from people_gator_api.routes.v1.users import router as users_router
from people_gator_api.routes.v1.root import router as root_router
from people_gator_api.routes.v1.search import router as search_router
from people_gator_api.routes.v1.sources import router as sources_router

router = APIRouter(prefix="/api/v1")
router.include_router(search_router)
router.include_router(identities_router)
router.include_router(annotations_router)
router.include_router(sources_router)
router.include_router(media_router)
router.include_router(page_layouts_router)
router.include_router(users_router)
router.include_router(root_router)

__all__ = ["router"]
