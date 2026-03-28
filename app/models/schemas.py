from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Common ────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    status_code: int


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int | None = None


class PaginatedResponse(BaseModel):
    data: list[Any]
    pagination: PaginationMeta


# ── Auth ──────────────────────────────────────────────────────────────────────

class AuthUser(BaseModel):
    github_user_id: str
    username: str
    avatar_url: str
    token_type: str
    scope: str


class TokenValidation(BaseModel):
    valid: bool
    username: str | None = None
    scopes: list[str] = []
    message: str


# ── Repository ────────────────────────────────────────────────────────────────

class RepoOwner(BaseModel):
    login: str
    avatar_url: str
    html_url: str


class Repository(BaseModel):
    id: int
    name: str
    full_name: str
    description: str | None = None
    private: bool
    fork: bool
    html_url: str
    language: str | None = None
    stargazers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    default_branch: str = "main"
    owner: RepoOwner
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── Issue ─────────────────────────────────────────────────────────────────────

class IssueUser(BaseModel):
    login: str
    avatar_url: str
    html_url: str


class IssueLabel(BaseModel):
    name: str
    color: str
    description: str | None = None


class Issue(BaseModel):
    id: int
    number: int
    title: str
    body: str | None = None
    state: str
    html_url: str
    user: IssueUser
    labels: list[IssueLabel] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
    closed_at: datetime | None = None


class CreateIssueRequest(BaseModel):
    owner: str = Field(..., min_length=1, description="Repository owner (username or org)")
    repo: str = Field(..., min_length=1, description="Repository name")
    title: str = Field(..., min_length=1, max_length=256, description="Issue title")
    body: str | None = Field(None, description="Issue body (markdown supported)")
    labels: list[str] = Field(default_factory=list, description="Labels to apply")
    assignees: list[str] = Field(default_factory=list, description="GitHub usernames to assign")


# ── Commit ────────────────────────────────────────────────────────────────────

class CommitAuthor(BaseModel):
    name: str
    email: str
    date: datetime | None = None


class CommitDetail(BaseModel):
    message: str
    author: CommitAuthor
    comment_count: int = 0


class Commit(BaseModel):
    sha: str
    html_url: str
    commit: CommitDetail
    author: IssueUser | None = None


# ── Pull Request ──────────────────────────────────────────────────────────────

class PRBranch(BaseModel):
    label: str
    ref: str
    sha: str


class PullRequest(BaseModel):
    id: int
    number: int
    title: str
    body: str | None = None
    state: str
    html_url: str
    user: IssueUser
    head: PRBranch
    base: PRBranch
    draft: bool = False
    merged: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreatePRRequest(BaseModel):
    owner: str = Field(..., min_length=1)
    repo: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, max_length=256)
    body: str | None = None
    head: str = Field(..., description="Branch name with your changes")
    base: str = Field(default="main", description="Branch to merge into")
    draft: bool = False
