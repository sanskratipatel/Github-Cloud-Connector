from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.database.db import get_db
from app.services import auth_service
from app.utils.logger import logger

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


@router.get(
    "/login",
    summary="Start GitHub OAuth flow",
    description="Redirects the user to GitHub's OAuth authorization page. "
                "Requires GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET to be set in .env.",
)
async def oauth_login() -> RedirectResponse:
    if not settings.has_oauth:
        raise HTTPException(
            status_code=501,
            detail=(
                "OAuth 2.0 is not configured on this server. "
                "Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in your .env file, "
                "then restart the server."
            ),
        )
    try:
        url, state = auth_service.generate_oauth_url()
        logger.info("Redirecting user to GitHub OAuth")
        return RedirectResponse(url=url)
    except Exception as exc:
        logger.exception(f"Failed to generate OAuth URL: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Failed to start the OAuth flow due to a server error. Please try again.",
        )


@router.get(
    "/callback",
    summary="GitHub OAuth callback",
    description="GitHub redirects here after the user grants access. "
                "Exchanges the authorization code for a token and stores it in SQLite.",
)
async def oauth_callback(
    code: str = Query(..., description="Authorization code from GitHub"),
    state: str = Query(..., description="CSRF state token"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # CSRF state validation — prevents forged callback attacks
    if not auth_service.validate_oauth_state(state):
        logger.warning("OAuth callback received with invalid or expired state token")
        raise HTTPException(
            status_code=400,
            detail=(
                "The OAuth state token is invalid or has expired. "
                "This can happen if you waited too long or refreshed the page. "
                "Please visit /auth/login to start a fresh login."
            ),
        )

    try:
        token_data = await auth_service.exchange_code_for_token(code)
    except ValueError as exc:
        logger.error(f"OAuth code exchange failed: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Unexpected error during OAuth code exchange: {exc}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while exchanging the authorization code. "
                   "Please try logging in again.",
        )

    try:
        user_data = await auth_service.fetch_github_user(token_data["access_token"])
    except ValueError as exc:
        logger.error(f"Failed to fetch GitHub user after OAuth: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Unexpected error fetching GitHub user after OAuth: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Authentication succeeded but we could not retrieve your GitHub profile. "
                   "Please try again.",
        )

    try:
        stored = await auth_service.upsert_oauth_token(
            db=db,
            github_user_id=str(user_data["id"]),
            username=user_data["login"],
            avatar_url=user_data.get("avatar_url", ""),
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "bearer"),
            scope=token_data.get("scope", ""),
        )
    except ValueError as exc:
        logger.error(f"Failed to save OAuth token for '{user_data.get('login')}': {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Unexpected error saving OAuth token: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Your GitHub session could not be saved. Please try logging in again.",
        )

    logger.info(f"OAuth login successful for user: {stored.username}")
    return {
        "message": "Authentication successful! You are now logged in.",
        "user": {
            "username": stored.username,
            "avatar_url": stored.avatar_url,
            "scope": stored.scope,
        },
        "hint": (
            f"Pass the header 'X-GitHub-Username: {stored.username}' "
            "in your API requests to authenticate automatically."
        ),
    }


@router.get(
    "/users",
    summary="List OAuth-authenticated users",
    description="Returns all users who have authenticated via OAuth and have tokens stored.",
)
async def list_oauth_users(db: AsyncSession = Depends(get_db)) -> list[dict]:
    try:
        users = await auth_service.list_authenticated_users(db)
        return [
            {
                "username": u.username,
                "avatar_url": u.avatar_url,
                "scope": u.scope,
                "authenticated_at": u.created_at,
            }
            for u in users
        ]
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Unexpected error listing OAuth users: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve the list of authenticated users. Please try again.",
        )


@router.get(
    "/validate",
    summary="Validate a GitHub token",
    description="Checks whether the provided GitHub PAT or OAuth token is valid "
                "and returns the associated username and granted scopes.",
)
async def validate_token(
    token: str = Query(..., description="GitHub PAT or OAuth token to validate"),
) -> dict:
    try:
        from app.services.github_service import validate_token as _validate
        result = await _validate(token)
        return result
    except Exception as exc:
        logger.exception(f"Unexpected error validating token: {exc}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while validating the token. Please try again.",
        )
