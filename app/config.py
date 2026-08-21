"""
Centralised configuration loaded from environment / .env file.
All secrets live here — no hard-coded credentials anywhere else.
"""

import json
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Database ────────────────────────────────────────────
    use_sqlite: bool = False                         # True for local SQLite dev
    sqlite_path: str = "./app.db"
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "dbname"
    db_user: str = "api_user"
    db_password: str = "change-me"

    # ── JWT / Auth ───────────────────────────────────────────
    secret_key: str = "replace-with-a-64-char-random-hex"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # ── App ──────────────────────────────────────────────────
    app_title: str = "SEF Internal Data API"
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000"

    # ── Table Aliases ────────────────────────────────────────
    # JSON mapping of  public_alias -> real_table_name
    # e.g.  TABLE_ALIASES={"appointments":"rpt_appointments","patients":"tbl_patient_master"}
    # Real table names are NEVER exposed in public API URLs or responses.
    table_aliases: str = "{}"

    @property
    def database_url(self) -> str:
        if self.use_sqlite:
            return f"sqlite:///{self.sqlite_path}"
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def alias_map(self) -> dict[str, str]:
        """Returns {public_alias: real_table_name} mapping."""
        try:
            return json.loads(self.table_aliases)
        except (json.JSONDecodeError, TypeError):
            return {}

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
