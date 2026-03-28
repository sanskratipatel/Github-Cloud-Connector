from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.database.db import get_db
from app.services.auth_service import get_token_by_username

settings = get_settings()

# Registers the Bearer security scheme in Swagger UI.
# auto_error=False means we handle the missing token ourselves with a friendly message.
bearer_scheme = HTTPBearer(
    scheme_name="GitHubToken",
    description=(
        "Enter your GitHub Personal Access Token (PAT) or OAuth token.\n\n"
        "Example: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`\n\n"
        "Create a PAT at: https://github.com/settings/tokens\n\n"
        "Required scopes: `repo`, `read:user`, `read:org`"
    ),
    auto_error=False,
)


async def get_github_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    x_github_token: str | None = Header(None, description="GitHub PAT or OAuth token"),
    x_github_username: str | None = Header(
        None, description="GitHub username to look up stored OAuth token"
    ),
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    Resolve a GitHub token from (in priority order):

    1. Swagger Authorize button  →  Authorization: Bearer ghp_xxx
    2. X-GitHub-Token header     →  direct PAT or OAuth token
    3. X-GitHub-Username header  →  look up stored OAuth token in SQLite
    4. GITHUB_TOKEN in .env      →  fallback for server-side default token
    """
    # 1. Bearer token from Swagger "Authorize" button or Authorization header
    if credentials and credentials.credentials:
        return credentials.credentials

    # 2. Direct token via custom header
    if x_github_token:
        return x_github_token

    # 3. Username header → look up OAuth token stored in SQLite
    if x_github_username:
        stored = await get_token_by_username(db, x_github_username)
        if stored:
            return stored.access_token
        raise HTTPException(
            status_code=401,
            detail=(
                f"No OAuth token found for GitHub username '{x_github_username}'. "
                "Please authenticate first by visiting /auth/login."
            ),
        )

    # 4. Fallback to server-side PAT from .env
    if settings.has_pat:
        return settings.github_token

    raise HTTPException(
        status_code=401,
        detail=(
            "Authentication required. Provide your GitHub token using one of these methods:\n"
            "• Swagger: click the 'Authorize' button (lock icon) and enter your token\n"
            "• Header: X-GitHub-Token: ghp_xxx\n"
            "• OAuth: X-GitHub-Username: your_login (after /auth/login)\n"
            "• Environment: set GITHUB_TOKEN in .env"
        ),
    )
