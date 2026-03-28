import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.config.settings import get_settings
from app.database.db import init_db
from app.routes import auth, commits, issues, pull_requests, repos
from app.services.github_service import GitHubAPIError
from app.utils.logger import logger, setup_logger

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    os.makedirs("logs", exist_ok=True)
    setup_logger(debug=settings.debug)
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    await init_db()
    logger.info("Database initialised")

    if settings.has_pat:
        logger.info("GitHub PAT detected in environment")
    else:
        logger.warning("No GitHub PAT found in .env — PAT-based auth will not work")

    if settings.has_oauth:
        logger.info("GitHub OAuth credentials detected")
    else:
        logger.info("GitHub OAuth not configured (optional)")

    yield

    logger.info("Shutting down GitHub Cloud Connector")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "A GitHub Cloud Connector that integrates with the GitHub API.\n\n"
        "---\n\n"
        "## How to authenticate in Swagger\n\n"
        "1. Click the **Authorize** button (🔒) at the top right of this page\n"
        "2. Enter your GitHub Personal Access Token in the **Value** field\n"
        "   - Format: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`\n"
        "   - Create one at: https://github.com/settings/tokens\n"
        "   - Required scopes: `repo`, `read:user`, `read:org`\n"
        "3. Click **Authorize** → **Close**\n"
        "4. All 🔒 locked endpoints will now use your token automatically\n\n"
        "---\n\n"
        "## Other authentication options\n\n"
        "| Method | How |\n"
        "|--------|-----|\n"
        "| Swagger UI | Click **Authorize** button above |\n"
        "| Direct header | `X-GitHub-Token: ghp_xxx` |\n"
        "| OAuth 2.0 | Visit `/auth/login`, then use `X-GitHub-Username: your_login` |\n"
        "| Env fallback | Set `GITHUB_TOKEN` in `.env` (auto-used if no header) |\n\n"
        "---\n\n"
        "## Rate limiting\n\n"
        "Responses are cached briefly to reduce GitHub API calls. "
        "GitHub allows **5,000 requests/hour** for authenticated users."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ── Custom OpenAPI schema — registers Bearer security scheme ──────────────────

def custom_openapi() -> dict:  # type: ignore[type-arg]
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # FastAPI auto-registers the "GitHubToken" Bearer scheme from the HTTPBearer dependency.
    # We just enrich its description here so Swagger shows helpful guidance.
    schemes = schema.get("components", {}).get("securitySchemes", {})
    if "GitHubToken" in schemes:
        schemes["GitHubToken"]["description"] = (
            "Enter your GitHub Personal Access Token (PAT) or OAuth token.\n\n"
            "**Example:** `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`\n\n"
            "**Create a PAT:** https://github.com/settings/tokens\n\n"
            "**Required scopes:** `repo`, `read:user`, `read:org`"
        )

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]


# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global Exception Handlers ─────────────────────────────────────────────────

@app.exception_handler(GitHubAPIError)
async def github_api_error_handler(request: Request, exc: GitHubAPIError) -> JSONResponse:
    logger.error(f"GitHub API Error [{exc.status_code}]: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "detail": exc.detail},
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(repos.router)
app.include_router(issues.router)
app.include_router(commits.router)
app.include_router(pull_requests.router)


# ── Public endpoints (no auth required) ──────────────────────────────────────

@app.get("/", tags=["Health"], summary="Root endpoint")
async def root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
        "auth_modes": {
            "pat_env": settings.has_pat,
            "oauth": settings.has_oauth,
        },
    }


@app.get("/health", tags=["Health"], summary="Health check")
async def health_check() -> dict:
    return {"status": "healthy"}
