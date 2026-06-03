from fastapi import APIRouter

from people_gator_api.routes.v1.root import router as root_router
from people_gator_api.routes.v1.clusters import router as clusters_router
from people_gator_api.routes.v1.evidence import router as evidence_router
from people_gator_api.routes.v1.exports import router as exports_router
from people_gator_api.routes.v1.principals import router as principals_router
from people_gator_api.routes.v1.search import router as search_router
from people_gator_api.routes.v1.sources import router as sources_router
from people_gator_api.routes.v1.tasks import router as tasks_router

router = APIRouter(prefix="/api/v1")
router.include_router(search_router)
router.include_router(clusters_router)
router.include_router(tasks_router)
router.include_router(sources_router)
router.include_router(evidence_router)
router.include_router(principals_router)
router.include_router(exports_router)
router.include_router(root_router)

__all__ = ["router"]
