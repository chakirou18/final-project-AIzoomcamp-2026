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
    demo_mode: bool = False
    session_secret: SecretStr | None = None
    session_secret_file: Path | None = None
    operator_secret: SecretStr | None = None
    operator_secret_file: Path | None = None
    recovery_secret: SecretStr | None = None
    recovery_secret_file: Path | None = None
    oncall_secret: SecretStr | None = None
    oncall_secret_file: Path | None = None
    telemetry_enabled: bool = False
    otlp_endpoint: str = "http://otel-collector:4318/v1/traces"
    log_directory: Path | None = None

    @model_validator(mode="after")
    def validate_control_credentials(self) -> "Settings":
        for name in ("operator", "recovery", "oncall"):
            secret = getattr(self, name + "_secret")
            path = getattr(self, name + "_secret_file")
            if path:
                if secret is not None:
                    raise ValueError("Configure only one control credential source")
                try:
                    secret = SecretStr(path.read_text(encoding="utf-8").strip())
                except OSError:
                    raise ValueError("Control credential file is not readable") from None
                setattr(self, name + "_secret", secret)
            if (
                name in {"recovery", "oncall"}
                and secret is not None
                and len(secret.get_secret_value()) < 32
            ):
                raise ValueError("Recovery credential must contain at least 32 characters")
        if (
            self.operator_secret
            and self.recovery_secret
            and self.operator_secret.get_secret_value() == self.recovery_secret.get_secret_value()
        ):
            raise ValueError("Operator and recovery credentials must be distinct")
        if self.oncall_secret and any(
            value and value.get_secret_value() == self.oncall_secret.get_secret_value()
            for value in [self.operator_secret, self.recovery_secret]
        ):
            raise ValueError("On-call credential must be distinct")
        return self

    def signing_key(self) -> bytes:
        if self.session_secret is not None and self.session_secret_file is not None:
            raise ValueError("Configure one session signing key source")
        value = self.session_secret.get_secret_value() if self.session_secret else None
        if self.session_secret_file:
            value = self.session_secret_file.read_text(encoding="utf-8").strip()
        if value is None or len(value) < 32:
            raise ValueError("Session signing key must contain at least 32 characters")
        return value.encode()

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
