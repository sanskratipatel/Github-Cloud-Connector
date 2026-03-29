from typing import Any

import httpx

from app.config.settings import get_settings
from app.utils.cache import cache
from app.utils.logger import logger

settings = get_settings()

GITHUB_API = settings.github_api_base


class GitHubAPIError(Exception):
    def __init__(self, message: str, status_code: int = 500, detail: str | None = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


def _build_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _handle_response(response: httpx.Response, action: str) -> Any:
    """Translate every non-2xx GitHub response into a friendly GitHubAPIError."""
    if response.status_code == 401:
        raise GitHubAPIError(
            "Your GitHub token is invalid or has expired. "
            "Please check the GITHUB_TOKEN by /auth/login.",
            401,
        )
    if response.status_code == 403:
        remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
        if remaining == "0":
            reset = response.headers.get("X-RateLimit-Reset", "unknown")
            raise GitHubAPIError(
                f"GitHub API rate limit exceeded. Your quota resets at timestamp {reset}. "
                "Please wait before making more requests.",
                429,
            )
        raise GitHubAPIError(
            f"Access denied. You does not have permission to perform this action. "
            ,
            403,
        )
    if response.status_code == 404:
        raise GitHubAPIError(
            f"Resource not found while trying to {action}. ",
            404,
        )
    if response.status_code == 409:
        raise GitHubAPIError(
            f"The resource may already exist or there is a merge conflict.",
            409,
        )
    if response.status_code == 422:
        try:
            body = response.json()
            detail = str(body.get("errors", body.get("message", "Unknown validation error")))
        except Exception:
            detail = response.text[:300]
        raise GitHubAPIError(
            f"GitHub rejected the request to {action} due to a validation error. "
            "Check that all required fields are correct.",
            422,
            detail=detail,
        )
    if response.status_code == 451:
        raise GitHubAPIError(
            f"This resource is unavailable for legal reasons: {action}.",
            451,
        )
    if not response.is_success:
        raise GitHubAPIError(
            f"GitHub returned unexpected error {response.status_code}",
            response.status_code,
            detail=response.text[:500],
        )
    return response.json()


def _wrap_network_error(exc: Exception, action: str) -> GitHubAPIError:
    if isinstance(exc, httpx.TimeoutException):
        return GitHubAPIError(
            f"GitHub timed out for this  {action}. "
            "Please try again after some time",
            504,
        )
    if isinstance(exc, httpx.ConnectError):
        return GitHubAPIError(
            f"Could not connect to GitHub for this {action}. "
            "try again.",
            503,
        )
    if isinstance(exc, httpx.RequestError):
        return GitHubAPIError(
            f"A network error occurred while trying to {action}: {exc}",
            503,
        )
    return GitHubAPIError(
        f"An unexpected error occurred while trying to {action}: {exc}",
        500,
    )



async def validate_token(token: str) -> dict[str, Any]:
    logger.debug("Validating GitHub token")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API}/user", headers=_build_headers(token), timeout=10
            )
    except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as exc:
        logger.warning(f"Token validation network error: {exc}")
        return {
            "valid": False,
            "username": None,
            "scopes": [],
            "message": "Could not reach GitHub to validate the token. Check your connection.",
        }
    except Exception as exc:
        logger.error(f"Unexpected error during token validation: {exc}")
        return {
            "valid": False,
            "username": None,
            "scopes": [],
            "message": f"Unexpected error during token validation: {exc}",
        }

    if response.status_code == 401:
        return {
            "valid": False,
            "username": None,
            "scopes": [],
            "message": "Invalid token. Please generate Token with appropriate scopes and try again.",
        }
    if response.is_success:
        data = response.json()
        scopes_header = response.headers.get("X-OAuth-Scopes", "")
        scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]
        logger.info(f"Token valid for user: {data.get('login')}")
        return {
            "valid": True,
            "username": data.get("login"),
            "scopes": scopes,
            "message": "Token is valid",
        }
    return {
        "valid": False,
        "username": None,
        "scopes": [],
        "message": f"Token validation returned HTTP {response.status_code}",
    }


async def fetch_user_repos(
    token: str, username: str | None = None, page: int = 1, per_page: int = 30
) -> list[dict[str, Any]]:
    cache_key = f"repos:{username or 'authenticated'}:{page}:{per_page}"
    cached = cache.get(cache_key)
    if cached:
        logger.debug(f"Cache hit for repos: {cache_key}")
        return cached  # type: ignore[return-value]

    params: dict[str, Any] = {"page": page, "per_page": min(per_page, 100), "sort": "updated"}

    if username:
        url = f"{GITHUB_API}/users/{username}/repos"
        params["type"] = "all"
    else:
        url = f"{GITHUB_API}/user/repos"
        params["affiliation"] = "owner,collaborator,organization_member"

    action = f"fetch repos for '{username or 'authenticated user'}'"
    logger.info(f"Fetching repos — {action} (page {page})")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url, headers=_build_headers(token), params=params, timeout=15
            )
    except Exception as exc:
        raise _wrap_network_error(exc, action)

    result = _handle_response(response, action)
    cache.set(cache_key, result, ttl=120)
    return result 


async def fetch_org_repos(
    token: str, org: str, page: int = 1, per_page: int = 30
) -> list[dict[str, Any]]:
    cache_key = f"org_repos:{org}:{page}:{per_page}"
    cached = cache.get(cache_key)
    if cached:
        return cached  

    action = f"fetch repos for organisation '{org}'"
    logger.info(f"Fetching org repos — {action} (page {page})")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API}/orgs/{org}/repos",
                headers=_build_headers(token),
                params={"page": page, "per_page": min(per_page, 100), "sort": "updated"},
                timeout=15,
            )
    except Exception as exc:
        raise _wrap_network_error(exc, action)

    result = _handle_response(response, action)
    cache.set(cache_key, result, ttl=120)
    return result  



async def fetch_issues(
    token: str,
    owner: str,
    repo: str,
    state: str = "open",
    page: int = 1,
    per_page: int = 30,
) -> list[dict[str, Any]]:
    cache_key = f"issues:{owner}/{repo}:{state}:{page}:{per_page}"
    cached = cache.get(cache_key)
    if cached:
        return cached  # type: ignore[return-value]

    action = f"fetch {state} issues from '{owner}/{repo}'"
    logger.info(f"Fetching issues — {action} (page {page})")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/issues",
                headers=_build_headers(token),
                params={
                    "state": state,
                    "page": page,
                    "per_page": min(per_page, 100),
                    "filter": "all",
                },
                timeout=15,
            )
    except Exception as exc:
        raise _wrap_network_error(exc, action)

    result = _handle_response(response, action)
    # GitHub's /issues endpoint also returns PRs — filter them out
    issues_only = [item for item in result if "pull_request" not in item]
    cache.set(cache_key, issues_only, ttl=60)
    return issues_only


async def create_issue(
    token: str,
    owner: str,
    repo: str,
    title: str,
    body: str | None = None,
    labels: list[str] | None = None,
    assignees: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"title": title}
    if body:
        payload["body"] = body
    if labels:
        payload["labels"] = labels
    if assignees:
        payload["assignees"] = assignees

    action = f"create issue in '{owner}/{repo}'"
    logger.info(f"Creating issue — {action}: {title!r}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GITHUB_API}/repos/{owner}/{repo}/issues",
                headers=_build_headers(token),
                json=payload,
                timeout=15,
            )
    except Exception as exc:
        raise _wrap_network_error(exc, action)

    result = _handle_response(response, action)
    cache.delete(f"issues:{owner}/{repo}:open:1:30")
    return result



async def fetch_commits(
    token: str,
    owner: str,
    repo: str,
    branch: str | None = None,
    page: int = 1,
    per_page: int = 30,
) -> list[dict[str, Any]]:
    cache_key = f"commits:{owner}/{repo}:{branch or 'default'}:{page}:{per_page}"
    cached = cache.get(cache_key)
    if cached:
        return cached 
    params: dict[str, Any] = {"page": page, "per_page": min(per_page, 100)}
    if branch:
        params["sha"] = branch

    action = f"fetch commits from '{owner}/{repo}'" + (f" (branch: {branch})" if branch else "")
    logger.info(f"Fetching commits — {action} (page {page})")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/commits",
                headers=_build_headers(token),
                params=params,
                timeout=15,
            )
    except Exception as exc:
        raise _wrap_network_error(exc, action)

    result = _handle_response(response, action)
    cache.set(cache_key, result, ttl=120)
    return result 




async def fetch_pull_requests(
    token: str,
    owner: str,
    repo: str,
    state: str = "open",
    page: int = 1,
    per_page: int = 30,
) -> list[dict[str, Any]]:
    cache_key = f"prs:{owner}/{repo}:{state}:{page}:{per_page}"
    cached = cache.get(cache_key)
    if cached:
        return cached  # type: ignore[return-value]

    action = f"fetch {state} pull requests from '{owner}/{repo}'"
    logger.info(f"Fetching PRs — {action} (page {page})")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
                headers=_build_headers(token),
                params={"state": state, "page": page, "per_page": min(per_page, 100)},
                timeout=15,
            )
    except Exception as exc:
        raise _wrap_network_error(exc, action)

    result = _handle_response(response, action)
    cache.set(cache_key, result, ttl=60)
    return result  


async def create_pull_request(
    token: str,
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str | None = None,
    draft: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": title,
        "head": head,
        "base": base,
        "draft": draft,
    }
    if body:
        payload["body"] = body

    action = f"create pull request in '{owner}/{repo}' ({head} → {base})"
    logger.info(f"Creating PR — {action}: {title!r}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
                headers=_build_headers(token),
                json=payload,
                timeout=15,
            )
    except Exception as exc:
        raise _wrap_network_error(exc, action)

    result = _handle_response(response, action)
    cache.delete(f"prs:{owner}/{repo}:open:1:30")
    return result
