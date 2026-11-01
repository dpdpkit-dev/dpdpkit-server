"""Entry point of the image: `python -m dpdpkit.server`."""

import getpass
import sys

import uvicorn

from dpdpkit.errors import ConfigError
from dpdpkit.server import auth
from dpdpkit.server.settings import Settings


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if args == ["new-api-key"]:
        key, key_hash = auth.generate_api_key()
        print(f"API key (shown once, give it to your backend): {key}")
        print(f"Hash (put it in DPDPKIT_API_KEY_HASHES): {key_hash}")
        return
    if args == ["hash-password"]:
        print(auth.hash_password(getpass.getpass("Admin password: ")))
        return
    if args:
        sys.exit("usage: python -m dpdpkit.server [new-api-key | hash-password]")
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
