"""Server settings from environment variables or a mounted ``dpdpkit.yaml``.

Precedence, highest first: environment variables, the ``server:`` section of ``dpdpkit.yaml``, defaults.
The rest of ``dpdpkit.yaml`` (purposes, notices, overlays) is read by dpdpkit-core, not here.

The config file is ``DPDPKIT_CONFIG`` if set (it must exist), else ``/etc/dpdpkit/dpdpkit.yaml`` or
``./dpdpkit.yaml`` when present. Secrets (``database_url``, ``signing_key``) can come from the environment,
or from a file named by ``DPDPKIT_DATABASE_URL_FILE`` / ``DPDPKIT_SIGNING_KEY_FILE`` (Docker and Kubernetes
secrets); they are not read from the YAML file, so the file is safe to commit.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dpdpkit.errors import ConfigError

DEFAULT_CONFIG_PATHS = (Path("/etc/dpdpkit/dpdpkit.yaml"), Path("dpdpkit.yaml"))
LOG_LEVELS = ("critical", "error", "warning", "info", "debug")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    host: str = "0.0.0.0"  # listens inside the container
    port: int = 8000
    log_level: str = "info"
    migrate_on_startup: bool = False
    config_path: Path | None = None
    database_url: str | None = field(default=None, repr=False)
    signing_key: str | None = field(default=None, repr=False)

    @classmethod
    def load(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        config_path = _find_config(env)
        file_values = _server_section(config_path)

        def pick(name: str) -> Any:
            value = env.get(f"DPDPKIT_{name.upper()}")
            return value if value not in (None, "") else file_values.get(name)

        defaults = cls()
        log_level = str(pick("log_level") or defaults.log_level).lower()
        if log_level not in LOG_LEVELS:
            raise ConfigError(f"log_level must be one of {', '.join(LOG_LEVELS)}, not {log_level!r}")
        return cls(
            host=str(pick("host") or defaults.host),
            port=_port(pick("port"), defaults.port),
            log_level=log_level,
            migrate_on_startup=_flag("migrate_on_startup", pick("migrate_on_startup"), defaults.migrate_on_startup),
            config_path=config_path,
            database_url=_secret(env, "DATABASE_URL"),
            signing_key=_secret(env, "SIGNING_KEY"),
        )


def _find_config(env: Mapping[str, str]) -> Path | None:
    explicit = env.get("DPDPKIT_CONFIG")
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise ConfigError(f"DPDPKIT_CONFIG points to {explicit}, which is not a file")
        return path
    return next((path for path in DEFAULT_CONFIG_PATHS if path.is_file()), None)


def _server_section(path: Path | None) -> Mapping[str, Any]:
    if path is None:
        return {}
    # Imported here so that plain env-only start-up does not need to parse YAML at all.
    from dpdpkit.config import load_config

    section = load_config(path).get("server") or {}
    if not isinstance(section, Mapping):
        raise ConfigError(f"{path}: server must be a mapping")
    for name in ("database_url", "signing_key"):
        if name in section:
            raise ConfigError(f"{path}: server.{name} is a secret; set DPDPKIT_{name.upper()} instead")
    return section


def _secret(env: Mapping[str, str], name: str) -> str | None:
    value, file_name = env.get(f"DPDPKIT_{name}"), env.get(f"DPDPKIT_{name}_FILE")
    if value and file_name:
        raise ConfigError(f"set only one of DPDPKIT_{name} and DPDPKIT_{name}_FILE")
    if file_name:
        try:
            return Path(file_name).read_text(encoding="utf-8").strip() or None
        except OSError as exc:
            raise ConfigError(f"cannot read DPDPKIT_{name}_FILE {file_name}: {exc}") from exc
    return value or None


def _port(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ConfigError(f"port must be a number, not {value!r}") from None
    if not 1 <= port <= 65535:
        raise ConfigError(f"port must be between 1 and 65535, not {port}")
    return port


def _flag(name: str, value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ConfigError(f"{name} must be true or false, not {value!r}")
