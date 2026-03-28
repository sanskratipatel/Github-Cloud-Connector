from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services import github_service
from app.services.github_service import GitHubAPIError
from app.utils.dependencies import get_github_token
from app.utils.logger import logger

router = APIRouter(prefix="/repos", tags=["Repositories"])

TokenDep = Annotated[str, Depends(get_github_token)]


def _github_error(exc: GitHubAPIError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _unexpected_error(exc: Exception, action: str) -> HTTPException:
    logger.exception(f"Unexpected error while {action}: {exc}")
    return HTTPException(
        status_code=500,
        detail=f"An unexpected server error occurred while {action}. Please try again later.",
    )


@router.get(
    "",
    summary="Fetch repositories for the authenticated user",
    description="Returns a paginated list of repositories for the authenticated user. "
                "Pass `username` to fetch a specific user's public repos instead.",
)
async def get_repos(
    token: TokenDep,
    username: str | None = Query(
        None, description="GitHub username (optional; uses authenticated user if omitted)"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(30, ge=1, le=100, description="Results per page (max 100)"),
) -> dict:
    try:
        repos = await github_service.fetch_user_repos(token, username, page, per_page)
        logger.info(f"Returning {len(repos)} repos (page {page})")
        return {
            "data": repos,
            "pagination": {"page": page, "per_page": per_page, "count": len(repos)},
        }
    except GitHubAPIError as exc:
        raise _github_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unexpected_error(exc, "fetching repositories")


@router.get(
    "/org/{org}",
    summary="Fetch repositories for an organization",
    description="Returns a paginated list of repositories belonging to the given GitHub organization.",
)
async def get_org_repos(
    org: str,
    token: TokenDep,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(30, ge=1, le=100, description="Results per page (max 100)"),
) -> dict:
    try:
        repos = await github_service.fetch_org_repos(token, org, page, per_page)
        logger.info(f"Returning {len(repos)} repos for org '{org}' (page {page})")
        return {
            "data": repos,
            "pagination": {"page": page, "per_page": per_page, "count": len(repos)},
        }
    except GitHubAPIError as exc:
        raise _github_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unexpected_error(exc, f"fetching repositories for organisation '{org}'")
