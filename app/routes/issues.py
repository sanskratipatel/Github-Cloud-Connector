from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.models.schemas import CreateIssueRequest
from app.services import github_service
from app.services.github_service import GitHubAPIError
from app.utils.dependencies import get_github_token
from app.utils.logger import logger

router = APIRouter(tags=["Issues"])

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
    "/issues",
    summary="List issues from a repository",
    description="Returns a paginated list of issues for the given `owner/repo`. "
                "Pull requests are automatically excluded from the results.",
)
async def list_issues(
    token: TokenDep,
    owner: str = Query(..., description="Repository owner (username or organisation)"),
    repo: str = Query(..., description="Repository name"),
    state: str = Query(
        "open",
        pattern="^(open|closed|all)$",
        description="Filter by issue state: open, closed, or all",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(30, ge=1, le=100, description="Results per page (max 100)"),
) -> dict:
    try:
        issues = await github_service.fetch_issues(token, owner, repo, state, page, per_page)
        logger.info(f"Returning {len(issues)} {state} issues from {owner}/{repo}")
        return {
            "data": issues,
            "pagination": {"page": page, "per_page": per_page, "count": len(issues)},
        }
    except GitHubAPIError as exc:
        raise _github_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unexpected_error(exc, f"listing issues from '{owner}/{repo}'")


@router.post(
    "/create-issue",
    summary="Create an issue in a repository",
    description="Creates a new GitHub issue. Requires write access to the repository.",
    status_code=201,
)
async def create_issue(token: TokenDep, body: CreateIssueRequest) -> dict:
    try:
        issue = await github_service.create_issue(
            token=token,
            owner=body.owner,
            repo=body.repo,
            title=body.title,
            body=body.body,
            labels=body.labels or None,
            assignees=body.assignees or None,
        )
        logger.info(f"Created issue #{issue.get('number')} in {body.owner}/{body.repo}")
        return {
            "message": "Issue created successfully",
            "issue": {
                "number": issue.get("number"),
                "title": issue.get("title"),
                "url": issue.get("html_url"),
                "state": issue.get("state"),
            },
        }
    except GitHubAPIError as exc:
        raise _github_error(exc)
    except HTTPException:
        raise
    except Exception as exc:
        raise _unexpected_error(exc, f"creating an issue in '{body.owner}/{body.repo}'")
