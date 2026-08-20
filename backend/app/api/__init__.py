from fastapi import APIRouter

from app.api.projects import router as projects_router
from app.api.datasources import router as datasources_router
from app.api.sessions import router as sessions_router
from app.api.schema import router as schema_router
from app.api.chat import router as chat_router

router = APIRouter()

router.include_router(projects_router)
router.include_router(datasources_router)
router.include_router(sessions_router)
router.include_router(schema_router)
router.include_router(chat_router)
