"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import init_db, check_db_connection
from app.core.rate_limit import limiter
from app.api.v1 import router as api_v1_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Initialize Sentry if DSN is configured
    sentry_dsn = getattr(settings, "sentry_dsn", None) or ""
    if sentry_dsn:
        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=0.1,
            send_default_pii=False,
        )
        logger.info("Sentry initialized for environment: %s", settings.environment)

    # Startup
    await init_db()
    yield
    # Shutdown (nothing needed)


app = FastAPI(
    title=settings.app_name,
    description="AI-powered Upwork job application automation with personalized cover letters",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware - allow all origins for Chrome extension compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Must be False when using wildcard origins
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_v1_router, prefix="/api/v1")



@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler so unhandled exceptions still get CORS headers.

    Starlette's ServerErrorMiddleware sits *outside* CORSMiddleware and sends
    500 responses without the Access-Control-Allow-Origin header, which causes
    the browser to report a CORS error instead of the real error.  Registering
    an explicit handler here keeps the response inside FastAPI's
    ExceptionMiddleware, which is inside CORSMiddleware.
    """
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/health")
async def health_check():
    """Health check endpoint for Render."""
    db_ok = await check_db_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "app": settings.app_name,
        "version": "0.1.0",
        "docs": "/docs",
    }
