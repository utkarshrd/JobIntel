"""
JobIntel - FastAPI Application Entry Point
AI-Powered Job Market Intelligence & Personalized Job Recommendation Platform.
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.core.database import init_db
from backend.app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management.
    Initializes database schema and loads initial resources on startup.
    """
    logger.info("Initializing JobIntel Backend Services...")
    try:
        init_db()
        logger.info("Database schema initialized.")
    except Exception as e:
        logger.warning(f"Database initialization warning: {e}")

    # Pre-compute the (2 s) analytics report in the background so the first dashboard visit is instant.
    import threading
    from backend.app.api.v1.endpoints.analytics import warm_twsma_cache
    threading.Thread(target=warm_twsma_cache, daemon=True).start()
    
    yield
    
    logger.info("Shutting down JobIntel Backend Services...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "AI-Powered Job Market Intelligence & Personalized Job Recommendation Platform. "
        "Transforms unstructured Indian job descriptions into structured market intelligence "
        "and delivers explainable, personalized recommendations."
    ),
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# Set CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)


WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web")
if os.path.isdir(WEB_DIR):
    # The web UI (plain HTML/CSS/JS, no build step) is served by the API itself: same origin, no second server.
    app.mount("/ui", StaticFiles(directory=WEB_DIR, html=True), name="ui")


@app.get("/", tags=["System"], include_in_schema=False)
def root(request: Request):
    """Browsers are sent to the web UI; API clients get a small JSON index."""
    if "text/html" in request.headers.get("accept", "") and os.path.isdir(WEB_DIR):
        return RedirectResponse("/ui/")
    return {
        "ui": "/ui/",
        "project": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": f"{settings.API_V1_STR}/docs",
        "health": f"{settings.API_V1_STR}/health",
        "description": "JobIntel Backend API is operational.",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=settings.DEBUG,
    )
