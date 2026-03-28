# GitHub Cloud Connector

A production-ready GitHub API integration built with **FastAPI** and **Python**.
Supports **Personal Access Token (PAT)** and **OAuth 2.0** authentication, SQLite token storage, in-memory caching, pagination, and full error handling.

---

## Features

- **Dual auth modes** — PAT (env-based) and GitHub OAuth 2.0
- **OAuth token persistence** — stored in SQLite via SQLAlchemy
- **In-memory TTL cache** — reduces GitHub API rate limit usage
- **Pagination** on all list endpoints
- **Structured error handling** — rate limits, 404s, auth failures
- **Request logging** with Loguru (console + rotating file)
- **Interactive API docs** at `/docs` (Swagger UI) and `/redoc`

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI 0.111 |
| HTTP client | httpx (async) |
| Database | SQLite + SQLAlchemy (async) |
| Settings | Pydantic-Settings |
| Logging | Loguru |
| Server | Uvicorn |

---

## Project Structure

```
Github-Cloud-Connector/
├── app/
│   ├── main.py              # FastAPI app, lifespan, routers
│   ├── config/
│   │   └── settings.py      # Pydantic-settings (reads .env)
│   ├── database/
│   │   └── db.py            # SQLAlchemy engine, OAuthToken model
│   ├── models/
│   │   └── schemas.py       # Pydantic request/response schemas
│   ├── routes/
│   │   ├── auth.py          # /auth/* — OAuth flow
│   │   ├── repos.py         # /repos
│   │   ├── issues.py        # /issues, /create-issue
│   │   ├── commits.py       # /commits
│   │   └── pull_requests.py # /pulls, /create-pr
│   ├── services/
│   │   ├── github_service.py  # All GitHub API calls
│   │   └── auth_service.py    # OAuth exchange + DB helpers
│   └── utils/
│       ├── cache.py         # TTL in-memory cache
│       ├── dependencies.py  # FastAPI token resolver dependency
│       └── logger.py        # Loguru setup
├── .env                     # Your secrets (git-ignored)
├── .env.example             # Template — copy to .env
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/Github-Cloud-Connector.git
cd Github-Cloud-Connector
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
# Required — GitHub Personal Access Token
GITHUB_TOKEN=ghp_your_token_here

# Optional — GitHub OAuth App credentials
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
GITHUB_REDIRECT_URI=http://localhost:8000/auth/callback

# App
SECRET_KEY=your-random-secret-key
DEBUG=false
```

**Creating a GitHub PAT:**
1. Go to [https://github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **Generate new token (classic)**
3. Select scopes: `repo`, `read:user`, `read:org`
4. Copy the token into `.env`

**Creating a GitHub OAuth App (optional):**
1. Go to [https://github.com/settings/developers](https://github.com/settings/developers)
2. Click **New OAuth App**
3. Set **Authorization callback URL** to `http://localhost:8000/auth/callback`
4. Copy Client ID and Secret into `.env`

### 5. Run the server

```bash
uvicorn app.main:app --reload
```

Server starts at **http://localhost:8000**

---

## API Reference

Open **http://localhost:8000/docs** for the interactive Swagger UI.

### Authentication

All endpoints accept a GitHub token via (in priority order):

| Method | Header | Description |
|--------|--------|-------------|
| PAT header | `X-GitHub-Token: ghp_xxx` | Direct token per request |
| OAuth username | `X-GitHub-Username: your_login` | Looks up stored OAuth token |
| Env fallback | *(none)* | Uses `GITHUB_TOKEN` from `.env` |

---

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | App info and auth status |
| GET | `/health` | Health check |

---

### Authentication (OAuth 2.0)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/login` | Redirect to GitHub OAuth |
| GET | `/auth/callback` | OAuth callback (called by GitHub) |
| GET | `/auth/users` | List OAuth-authenticated users |
| GET | `/auth/validate?token=xxx` | Validate any GitHub token |

**OAuth flow:**
1. Visit `GET /auth/login` → browser redirects to GitHub
2. Approve the app on GitHub
3. GitHub redirects to `/auth/callback` — token is stored in SQLite
4. Use `X-GitHub-Username: your_login` header in all subsequent API calls

---

### Repositories

| Method | Path | Description |
|--------|------|-------------|
| GET | `/repos` | List repos for authenticated user |
| GET | `/repos?username=torvalds` | List repos for a specific user |
| GET | `/repos?page=2&per_page=10` | Paginated results |
| GET | `/repos/org/{org}` | List repos for an organization |

**Example:**
```bash
curl -H "X-GitHub-Token: ghp_xxx" \
  "http://localhost:8000/repos?username=octocat&per_page=5"
```

---

### Issues

| Method | Path | Description |
|--------|------|-------------|
| GET | `/issues?owner=x&repo=y` | List open issues |
| GET | `/issues?owner=x&repo=y&state=closed` | List closed issues |
| POST | `/create-issue` | Create a new issue |

**List issues example:**
```bash
curl -H "X-GitHub-Token: ghp_xxx" \
  "http://localhost:8000/issues?owner=octocat&repo=Hello-World"
```

**Create issue example:**
```bash
curl -X POST "http://localhost:8000/create-issue" \
  -H "X-GitHub-Token: ghp_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "your-username",
    "repo": "your-repo",
    "title": "Bug: something is broken",
    "body": "Steps to reproduce...",
    "labels": ["bug"]
  }'
```

---

### Commits

| Method | Path | Description |
|--------|------|-------------|
| GET | `/commits?owner=x&repo=y` | List commits (default branch) |
| GET | `/commits?owner=x&repo=y&branch=dev` | Filter by branch |

**Example:**
```bash
curl -H "X-GitHub-Token: ghp_xxx" \
  "http://localhost:8000/commits?owner=octocat&repo=Hello-World&per_page=10"
```

---

### Pull Requests

| Method | Path | Description |
|--------|------|-------------|
| GET | `/pulls?owner=x&repo=y` | List open PRs |
| GET | `/pulls?owner=x&repo=y&state=closed` | List closed PRs |
| POST | `/create-pr` | Create a pull request |

**Create PR example:**
```bash
curl -X POST "http://localhost:8000/create-pr" \
  -H "X-GitHub-Token: ghp_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "owner": "your-username",
    "repo": "your-repo",
    "title": "feat: add new feature",
    "head": "feature-branch",
    "base": "main",
    "body": "## Summary\n- Added X\n- Fixed Y"
  }'
```

---

## Deploying to Render

1. Push your code to GitHub (make sure `.env` is in `.gitignore`)
2. Go to [https://render.com](https://render.com) → **New Web Service**
3. Connect your GitHub repository
4. Set these values:

| Setting | Value |
|---------|-------|
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

5. Add **Environment Variables** in the Render dashboard:
   - `GITHUB_TOKEN`
   - `GITHUB_CLIENT_ID` *(if using OAuth)*
   - `GITHUB_CLIENT_SECRET` *(if using OAuth)*
   - `GITHUB_REDIRECT_URI` → `https://your-app.onrender.com/auth/callback`
   - `SECRET_KEY` → a random string
   - `DEBUG` → `false`

> Note: SQLite will work on Render's free tier but data resets on deploy.
> For persistent OAuth storage, migrate `DATABASE_URL` to PostgreSQL.

---

## Error Responses

All errors return a consistent JSON structure:

```json
{
  "error": "Human-readable error message",
  "detail": "Additional context (optional)"
}
```

| HTTP Status | Meaning |
|-------------|---------|
| 400 | Bad request / validation error |
| 401 | Missing or invalid token |
| 403 | Token lacks required permissions |
| 404 | Resource not found |
| 422 | GitHub validation error |
| 429 | GitHub API rate limit exceeded |
| 500 | Internal server error |

---

## Development

```bash
# Run with auto-reload
uvicorn app.main:app --reload --port 8000

# View logs
tail -f logs/app.log
```

---

## Security Notes

- Never commit `.env` to version control
- `.env` is listed in `.gitignore`
- OAuth state tokens are single-use (CSRF protection)
- All inputs are validated via Pydantic before API calls
