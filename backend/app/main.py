from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.emails import router as emails_router
from app.api.documents import router as documents_router
from app.api.pdf import router as pdf_router
from app.api.classify import router as classify_router
from app.api.extract_icsr import router as extract_icsr_router
from app.api.ai import router as ai_router
from app.core.config import settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    init_db()
    yield


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.APP_NAME,
        description="Smart Inbox Assistant backend API for healthcare email and document processing.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS Configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include Routers
    application.include_router(health_router, prefix=settings.API_V1_PREFIX)
    application.include_router(documents_router, prefix=settings.API_V1_PREFIX)
    application.include_router(pdf_router, prefix=settings.API_V1_PREFIX)
    application.include_router(classify_router, prefix=settings.API_V1_PREFIX)
    application.include_router(extract_icsr_router, prefix=settings.API_V1_PREFIX)
    application.include_router(emails_router, prefix=settings.API_V1_PREFIX)
    # application.include_router(ai_router, prefix=settings.API_V1_PREFIX)  # disabled for mock mode

    return application


app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=(settings.APP_ENV == "development"),
    )

