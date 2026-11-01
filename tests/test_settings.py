from pathlib import Path

import pytest

from dpdpkit.errors import ConfigError
from dpdpkit.server.app import create_app
from dpdpkit.server.settings import Settings


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def write_yaml(path: Path, server: str = "") -> Path:
    path.write_text(f"policy: dpdp-rules-2025.v1\n{server}", encoding="utf-8")
    return path


def test_defaults() -> None:
    settings = Settings.load({})
    assert (settings.host, settings.port, settings.log_level) == ("0.0.0.0", 8000, "info")
    assert settings.config_path is None
    assert settings.database_url is None
    assert settings.migrate_on_startup is False


def test_environment() -> None:
    env = {
        "DPDPKIT_HOST": "127.0.0.1",
        "DPDPKIT_PORT": "9000",
        "DPDPKIT_LOG_LEVEL": "DEBUG",
        "DPDPKIT_MIGRATE_ON_STARTUP": "true",
        "DPDPKIT_DATABASE_URL": "postgresql://u:p@db/app",
    }
    settings = Settings.load(env)
    assert (settings.host, settings.port, settings.log_level) == ("127.0.0.1", 9000, "debug")
    assert settings.migrate_on_startup is True
    assert settings.database_url == "postgresql://u:p@db/app"
    assert "postgresql" not in repr(settings)


def test_yaml_server_section_and_env_precedence(tmp_path: Path) -> None:
    config = write_yaml(
        tmp_path / "mounted.yaml", "server:\n  port: 9100\n  log_level: warning\n  migrate_on_startup: true\n"
    )
    settings = Settings.load({"DPDPKIT_CONFIG": str(config), "DPDPKIT_PORT": "9200"})
    assert settings.config_path == config
    assert settings.port == 9200  # environment wins
    assert settings.log_level == "warning"
    assert settings.migrate_on_startup is True


def test_default_config_in_working_directory() -> None:
    write_yaml(Path("dpdpkit.yaml"), "server:\n  port: 9300\n")
    settings = Settings.load({})
    assert settings.config_path == Path("dpdpkit.yaml")
    assert settings.port == 9300


def test_missing_explicit_config() -> None:
    with pytest.raises(ConfigError, match="not a file"):
        Settings.load({"DPDPKIT_CONFIG": "nope.yaml"})


def test_secrets_not_allowed_in_yaml(tmp_path: Path) -> None:
    config = write_yaml(tmp_path / "c.yaml", "server:\n  database_url: sqlite://\n")
    with pytest.raises(ConfigError, match="DPDPKIT_DATABASE_URL"):
        Settings.load({"DPDPKIT_CONFIG": str(config)})


def test_secret_from_file(tmp_path: Path) -> None:
    key = tmp_path / "key"
    key.write_text("s3cret\n", encoding="utf-8")
    assert Settings.load({"DPDPKIT_SIGNING_KEY_FILE": str(key)}).signing_key == "s3cret"
    with pytest.raises(ConfigError, match="only one"):
        Settings.load({"DPDPKIT_SIGNING_KEY_FILE": str(key), "DPDPKIT_SIGNING_KEY": "x"})
    with pytest.raises(ConfigError, match="cannot read"):
        Settings.load({"DPDPKIT_SIGNING_KEY_FILE": str(tmp_path / "missing")})


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"DPDPKIT_PORT": "abc"}, "port must be a number"),
        ({"DPDPKIT_PORT": "70000"}, "between 1 and 65535"),
        ({"DPDPKIT_LOG_LEVEL": "loud"}, "log_level"),
        ({"DPDPKIT_MIGRATE_ON_STARTUP": "maybe"}, "true or false"),
    ],
)
def test_invalid_values(env: dict[str, str], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        Settings.load(env)


def test_app_carries_settings() -> None:
    settings = Settings(port=1234)
    assert create_app(settings).state.settings is settings
