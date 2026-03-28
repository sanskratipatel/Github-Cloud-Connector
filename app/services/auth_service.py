import secrets
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.database.db import OAuthToken
from app.utils.logger import logger

settings = get_settings()

# Temporary store for OAuth state params (CSRF protection)
_oauth_states: dict[str, bool] = {}


def generate_oauth_url() -> tuple[str, str]:
    """Generate a GitHub OAuth authorization URL with a one-time CSRF state token."""
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = True

    scope = "repo read:user read:org"
    url = (
        f"{settings.github_oauth_authorize}"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_redirect_uri}"
        f"&scope={scope}"
        f"&state={state}"
    )
    logger.debug(f"Generated OAuth URL with state={state[:8]}...")
    return url, state


def validate_oauth_state(state: str) -> bool:
    """Validate and consume a one-time OAuth state token (prevents CSRF)."""
    if state in _oauth_states:
        del _oauth_states[state]
        return True
    return False


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    """Exchange the GitHub OAuth authorization code for an access token."""
    logger.info("Exchanging OAuth code for access token")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.github_oauth_token,
                headers={"Accept": "application/json"},
                json={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": settings.github_redirect_uri,
                },
                timeout=15,
            )
    except httpx.TimeoutException:
        raise ValueError(
            "The request to GitHub timed out while exchanging the authorization code. "
            "Please try logging in again."
        )
    except httpx.ConnectError:
        raise ValueError(
            "Could not connect to GitHub to complete authentication. "
            "Check your internet connection and try again."
        )
    except httpx.RequestError as exc:
        raise ValueError(f"Network error during OAuth token exchange: {exc}")
    except Exception as exc:
        logger.error(f"Unexpected error during OAuth token exchange: {exc}")
        raise ValueError(f"An unexpected error occurred during authentication: {exc}")

    if not response.is_success:
        raise ValueError(
            f"GitHub declined the token exchange request (HTTP {response.status_code}). "
            "The authorization code may have expired — please try logging in again."
        )

    try:
        data = response.json()
    except Exception:
        raise ValueError("GitHub returned an unreadable response during token exchange.")

    if "error" in data:
        error_desc = data.get("error_description", data["error"])
        raise ValueError(f"GitHub OAuth error: {error_desc}")

    return data


async def fetch_github_user(access_token: str) -> dict[str, Any]:
    """Fetch GitHub user profile using an access token."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.github_api_base}/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
                timeout=10,
            )
    except httpx.TimeoutException:
        raise ValueError(
            "Timed out while fetching your GitHub profile. Please try logging in again."
        )
    except httpx.ConnectError:
        raise ValueError(
            "Could not connect to GitHub to fetch your profile. Check your internet connection."
        )
    except httpx.RequestError as exc:
        raise ValueError(f"Network error while fetching GitHub user profile: {exc}")
    except Exception as exc:
        logger.error(f"Unexpected error fetching GitHub user: {exc}")
        raise ValueError(f"Unexpected error while fetching your GitHub profile: {exc}")

    if response.status_code == 401:
        raise ValueError(
            "The access token was rejected by GitHub when fetching your profile. "
            "Please log in again."
        )
    if not response.is_success:
        raise ValueError(
            f"GitHub returned HTTP {response.status_code} when fetching your profile. "
            "Please try logging in again."
        )

    try:
        return response.json()
    except Exception:
        raise ValueError("GitHub returned an unreadable user profile response.")


async def upsert_oauth_token(
    db: AsyncSession,
    github_user_id: str,
    username: str,
    avatar_url: str,
    access_token: str,
    token_type: str,
    scope: str,
) -> OAuthToken:
    """Insert or update an OAuth token record in SQLite."""
    try:
        result = await db.execute(
            select(OAuthToken).where(OAuthToken.github_user_id == github_user_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.access_token = access_token
            existing.token_type = token_type
            existing.scope = scope
            existing.avatar_url = avatar_url
            logger.info(f"Updated OAuth token for user: {username}")
        else:
            existing = OAuthToken(
                github_user_id=github_user_id,
                username=username,
                avatar_url=avatar_url,
                access_token=access_token,
                token_type=token_type,
                scope=scope,
            )
            db.add(existing)
            logger.info(f"Stored new OAuth token for user: {username}")

        await db.commit()
        await db.refresh(existing)
        return existing

    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error(f"Database error saving OAuth token for '{username}': {exc}")
        raise ValueError(
            "Failed to save your authentication token to the database. "
            "Please try logging in again."
        )
    except Exception as exc:
        await db.rollback()
        logger.error(f"Unexpected error saving OAuth token for '{username}': {exc}")
        raise ValueError(f"An unexpected error occurred while saving your session: {exc}")


async def get_token_by_username(db: AsyncSession, username: str) -> OAuthToken | None:
    """Retrieve stored OAuth token by GitHub username."""
    try:
        result = await db.execute(
            select(OAuthToken).where(OAuthToken.username == username)
        )
        return result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.error(f"Database error looking up token for '{username}': {exc}")
        return None
    except Exception as exc:
        logger.error(f"Unexpected error looking up token for '{username}': {exc}")
        return None


async def list_authenticated_users(db: AsyncSession) -> list[OAuthToken]:
    """List all users who have authenticated via OAuth."""
    try:
        result = await db.execute(select(OAuthToken))
        return list(result.scalars().all())
    except SQLAlchemyError as exc:
        logger.error(f"Database error listing OAuth users: {exc}")
        raise ValueError("Could not retrieve the list of authenticated users from the database.")
    except Exception as exc:
        logger.error(f"Unexpected error listing OAuth users: {exc}")
        raise ValueError(f"An unexpected error occurred while listing authenticated users: {exc}")
