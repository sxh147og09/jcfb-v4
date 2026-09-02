"""Lazy PostgreSQL driver discovery and redaction-safe connection adapter."""

from __future__ import annotations

import importlib
import importlib.util
import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Protocol, Tuple


class ConnectionConfigError(ValueError):
    """Raised when the process environment cannot form a safe DB config."""


class DriverUnavailable(RuntimeError):
    """Raised when no supported PostgreSQL driver is installed."""


@dataclass(frozen=True)
class ConnectionSettings:
    """Non-persistent connection settings; ``password`` is never serialised."""

    host: str
    port: int
    database: str
    user: str
    password: str
    sslmode: str
    password_env_name: str = "JCFB_V4_RUNTIME_DB_PASSWORD"

    @classmethod
    def from_environment(cls, env: Optional[Mapping[str, str]] = None) -> "ConnectionSettings":
        values = dict(env or os.environ)
        aliases = {
            "host": ("JCFB_V4_RUNTIME_DB_HOST",),
            "port": ("JCFB_V4_RUNTIME_DB_PORT",),
            "database": ("JCFB_V4_RUNTIME_DB_NAME", "JCFB_V4_RUNTIME_DB"),
            "user": ("JCFB_V4_RUNTIME_DB_USER", "JCFB_V4_RUNTIME_OWNER"),
            "password": ("JCFB_V4_RUNTIME_DB_PASSWORD", "JCFB_V4_RUNTIME_PASSWORD"),
            "sslmode": ("JCFB_V4_RUNTIME_DB_SSLMODE",),
        }
        resolved: Dict[str, str] = {}
        missing = []
        for field, names in aliases.items():
            value = next((values.get(name) for name in names if values.get(name)), None)
            if value is None or not str(value).strip():
                missing.append(names[0])
            else:
                resolved[field] = str(value).strip()
        if missing:
            raise ConnectionConfigError("Required runtime connection environment variables are missing: " + ", ".join(missing))
        if "://" in resolved["host"] or "/" in resolved["host"]:
            raise ConnectionConfigError("Runtime database host must be a host name or IP, not a URL")
        try:
            port = int(resolved["port"])
        except ValueError as exc:
            raise ConnectionConfigError("Runtime database port must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ConnectionConfigError("Runtime database port is outside the valid range")
        if resolved["sslmode"] not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
            raise ConnectionConfigError("Runtime database sslmode is not supported")
        return cls(
            host=resolved["host"],
            port=port,
            database=resolved["database"],
            user=resolved["user"],
            password=resolved["password"],
            sslmode=resolved["sslmode"],
            password_env_name="JCFB_V4_RUNTIME_DB_PASSWORD" if values.get("JCFB_V4_RUNTIME_DB_PASSWORD") else "JCFB_V4_RUNTIME_PASSWORD",
        )

    def safe_dict(self) -> Dict[str, Any]:
        """Return report-safe settings without the password or a URL."""

        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "sslmode": self.sslmode,
            "credential_env_name": self.password_env_name,
        }


class ConnectionAdapter(Protocol):
    def connect(self, settings: ConnectionSettings) -> Any:
        ...

    def close(self, connection: Any) -> None:
        ...


def discover_driver() -> Tuple[Optional[str], Optional[Any]]:
    """Return the first supported driver without opening a connection."""

    for name in ("psycopg", "psycopg2"):
        if importlib.util.find_spec(name) is None:
            continue
        try:
            return name, importlib.import_module(name)
        except Exception:
            # Import failures are represented as an unavailable dependency; no
            # module exception or environment value is emitted.
            return None, None
    return None, None


def driver_status() -> Dict[str, Any]:
    name, _driver = discover_driver()
    if name:
        return {
            "status": "READY",
            "driver": name,
            "supported_drivers": ["psycopg", "psycopg2"],
            "connection_opened": False,
        }
    return {
        "status": "BLOCKED_DEPENDENCY",
        "driver": None,
        "supported_drivers": ["psycopg", "psycopg2"],
        "connection_opened": False,
        "reason": "Install psycopg in the F-drive project virtual environment before local runtime apply",
    }


class PostgresConnectionAdapter:
    """DB-API adapter with lazy import and no URL/string logging."""

    def __init__(self, driver: Optional[Any] = None, driver_name: Optional[str] = None):
        if driver is None:
            detected_name, detected_driver = discover_driver()
            self.driver_name = driver_name or detected_name
            self.driver = detected_driver
        else:
            self.driver_name = driver_name or getattr(driver, "__name__", "injected")
            self.driver = driver

    def status(self) -> Dict[str, Any]:
        if self.driver is None:
            result = driver_status()
            if self.driver_name:
                result["driver"] = self.driver_name
            return result
        return {
            "status": "READY",
            "driver": self.driver_name,
            "supported_drivers": ["psycopg", "psycopg2"],
            "connection_opened": False,
        }

    def connect(self, settings: ConnectionSettings) -> Any:
        if self.driver is None:
            raise DriverUnavailable("No supported PostgreSQL driver is installed")
        # Use keyword arguments instead of a connection URL so credentials can
        # never be reproduced in a report or command line.
        return self.driver.connect(
            host=settings.host,
            port=settings.port,
            dbname=settings.database,
            user=settings.user,
            password=settings.password,
            sslmode=settings.sslmode,
        )

    def close(self, connection: Any) -> None:
        close = getattr(connection, "close", None)
        if callable(close):
            close()
