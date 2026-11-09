"""Validated environment settings; secret values are never part of public health output."""

from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FIELDOPS_", extra="ignore", hide_input_in_errors=True
    )

    environment: str = "local"
    log_level: str = "INFO"
    db_host: str = "localhost"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "fieldops"
    db_user: str = "fieldops"
    db_password: SecretStr | None = None
    db_password_file: Path | None = None
    db_connect_timeout: int = Field(default=2, ge=1, le=10)

    @model_validator(mode="after")
    def validate_password_source(self) -> "Settings":
        if self.db_password is not None and self.db_password_file is not None:
            raise ValueError("Configure one database password source, not both")
        if self.db_password_file is not None:
            try:
                password = self.db_password_file.read_text(encoding="utf-8").strip()
            except OSError:
                raise ValueError("Database password file is not readable") from None
            self.db_password = SecretStr(password)
        if self.db_password is None or not self.db_password.get_secret_value():
            raise ValueError("A nonempty database password or password file is required")
        return self

    def database_url(self) -> URL:
        # URL.create safely escapes passwords; never interpolate or log connection strings.
        assert self.db_password is not None
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
