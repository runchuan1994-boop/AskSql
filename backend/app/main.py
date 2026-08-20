from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.core.config import settings
from app.core.database import init_db


def create_app() -> FastAPI:
    """Application factory for the FastAPI app."""
    app = FastAPI(title=settings.app_name, debug=settings.debug)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize database on startup
    init_db()

    # Register API router
    app.include_router(api_router, prefix="/api")

    @app.get("/health", tags=["health"])
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "ok",
            "app_name": settings.app_name,
            "debug": settings.debug,
        }

    return app


app = create_app()
