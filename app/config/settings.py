from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_name: str = "GitHub Cloud Connector"
    app_version: str = "1.0.0"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # GitHub PAT
    github_token: str = ""

    # GitHub OAuth 2.0
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/auth/callback"

    # Database
    database_url: str = "sqlite+aiosqlite:///./github_connector.db"

    # GitHub API base
    github_api_base: str = "https://api.github.com"
    github_oauth_authorize: str = "https://github.com/login/oauth/authorize"
    github_oauth_token: str = "https://github.com/login/oauth/access_token"

    @property
    def has_pat(self) -> bool:
        return bool(self.github_token and not self.github_token.startswith("ghp_your"))

    @property
    def has_oauth(self) -> bool:
        return bool(self.github_client_id and not self.github_client_id.startswith("your_"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
