from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.schemas import CreatePRRequest
from app.services import github_service
from app.services.github_service import GitHubAPIError
from app.utils.dependencies import get_github_token
from app.utils.logger import logger

router = APIRouter(tags=["Pull Requests"])

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
    "/pulls",
    summary="List pull requests from a repository",
    description="Returns a paginated list of pull requests for the given `owner/repo`.",
)
async def list_pull_requests(
    token: TokenDep,
    owner: str = Query(..., description="Repository owner (username or organisation)"),
    repo: str = Query(..., description="Repository name"),
    state: str = Query(
        "open",
        pattern="^(open|closed|all)$",
        description="Filter by PR state: open, closed, or all",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(30, ge=1, le=100, description="Results per page (max 100)"),
) -> dict:
    try:
        prs = await github_service.fetch_pull_requests(token, owner, repo, state, page, per_page)
        logger.info(f"Returning {len(prs)} {state} PRs from {owner}/{repo}")
        return {
            "data": prs,
            "pagination": {"page": page, "per_page": per_page, "count": len(prs)},
        }
    except GitHubAPIError as exc:
        raise _github_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unexpected_error(exc, f"listing pull requests from '{owner}/{repo}'")


@router.post(
    "/create-pr",
    summary="Create a pull request",
    description="Creates a new pull request merging `head` into `base`. "
                "Requires write access to the repository.",
    status_code=201,
)
async def create_pull_request(token: TokenDep, body: CreatePRRequest) -> dict:
    try:
        pr = await github_service.create_pull_request(
            token=token,
            owner=body.owner,
            repo=body.repo,
            title=body.title,
            head=body.head,
            base=body.base,
            body=body.body,
            draft=body.draft,
        )
        logger.info(f"Created PR #{pr.get('number')} in {body.owner}/{body.repo}")
        return {
            "message": "Pull request created successfully",
            "pull_request": {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "url": pr.get("html_url"),
                "state": pr.get("state"),
                "head": pr.get("head", {}).get("ref"),
                "base": pr.get("base", {}).get("ref"),
            },
        }
    except GitHubAPIError as exc:
        raise _github_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unexpected_error(exc, f"creating a pull request in '{body.owner}/{body.repo}'")
