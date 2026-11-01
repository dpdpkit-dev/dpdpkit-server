"""Entry point of the image: `python -m dpdpkit.server`."""

import sys

import uvicorn

from dpdpkit.errors import ConfigError
from dpdpkit.server.settings import Settings


def main() -> None:
    try:
        settings = Settings.load()
    except ConfigError as exc:
        sys.exit(f"dpdpkit-server: configuration error: {exc}")
    uvicorn.run(
        "dpdpkit.server.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
