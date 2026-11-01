"""Entry point of the image: `python -m dpdpkit.server`."""

import getpass
import sys

import uvicorn

from dpdpkit.errors import ConfigError
from dpdpkit.server import auth
from dpdpkit.server.app import create_app
from dpdpkit.server.engine import build_dpdpkit
from dpdpkit.server.metrics import Metrics
from dpdpkit.server.settings import Settings
from dpdpkit.server.worker import run_worker


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
    if args not in ([], ["worker"]):
        sys.exit("usage: python -m dpdpkit.server [worker | new-api-key | hash-password]")
    try:
        settings = Settings.load()
        if args == ["worker"]:
            _run_worker(settings)
            return
        # An app factory, so that the app is built after uvicorn has started and any problem is logged by it.
        uvicorn.run(
            "dpdpkit.server.app:create_app",
            factory=True,
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level,
        )
    except ConfigError as exc:
        sys.exit(f"dpdpkit-server: configuration error: {exc}")


def _run_worker(settings: Settings) -> None:
    """Run the periodic jobs, and serve the probes and metrics on the usual port for the container healthcheck."""
    dpdp = build_dpdpkit(settings)
    if dpdp is None:
        raise ConfigError("the worker needs DPDPKIT_DATABASE_URL")
    metrics = Metrics()
    _, stop, thread = run_worker(dpdp, metrics)
    try:
        uvicorn.run(
            create_app(settings, dpdp, metrics),
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level,
        )
    finally:
        stop.set()
        thread.join(timeout=10)


if __name__ == "__main__":
    main()
