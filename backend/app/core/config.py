import os
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Info
    APP_NAME: str = "Smart Inbox Assistant"
    APP_ENV: str = "development"
    APP_PORT: int = 8000
    USE_MOCK_DATA: bool = False
    APP_HOST: str = "0.0.0.0"
    API_V1_PREFIX: str = "/api"

    # CORS
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:4200"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Gemini AI
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Database (Oracle / SQLAlchemy)
    # Full connection URL format for Oracle:
    # oracle+oracledb://username:password@hostname:1521/?service_name=ORCLPDB1
    DATABASE_URL: str = "sqlite:///./smart_inbox.db"

    # Optional individual Oracle connection settings
    ORACLE_USER: str = ""
    ORACLE_PASSWORD: str = ""
    ORACLE_HOST: str = "localhost"
    ORACLE_PORT: int = 1521
    ORACLE_SERVICE_NAME: str = "ORCLPDB1"

    def get_database_url(self) -> str:
        """Returns configured DATABASE_URL or constructs Oracle URL from individual variables if provided."""
        if self.ORACLE_USER and self.ORACLE_PASSWORD:
            return (
                f"oracle+oracledb://{self.ORACLE_USER}:{self.ORACLE_PASSWORD}"
                f"@{self.ORACLE_HOST}:{self.ORACLE_PORT}/?service_name={self.ORACLE_SERVICE_NAME}"
            )
        return self.DATABASE_URL

    # Email Settings (IMAP)
    IMAP_SERVER: str = ""
    IMAP_PORT: int = 993
    IMAP_USERNAME: str = ""
    IMAP_PASSWORD: str = ""
    IMAP_USE_SSL: bool = True

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
