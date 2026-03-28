from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services import github_service
from app.services.github_service import GitHubAPIError
from app.utils.dependencies import get_github_token
from app.utils.logger import logger

router = APIRouter(tags=["Commits"])

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
    "/commits",
    summary="Fetch commits from a repository",
    description="Returns a paginated list of commits. Optionally filter by branch name.",
)
async def get_commits(
    token: TokenDep,
    owner: str = Query(..., description="Repository owner (username or organisation)"),
    repo: str = Query(..., description="Repository name"),
    branch: str | None = Query(
        None, description="Branch name to filter commits (uses default branch if omitted)"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(30, ge=1, le=100, description="Results per page (max 100)"),
) -> dict:
    try:
        commits = await github_service.fetch_commits(token, owner, repo, branch, page, per_page)
        logger.info(f"Returning {len(commits)} commits from {owner}/{repo}")
        return {
            "data": commits,
            "pagination": {"page": page, "per_page": per_page, "count": len(commits)},
        }
    except GitHubAPIError as exc:
        raise _github_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unexpected_error(exc, f"fetching commits from '{owner}/{repo}'")
