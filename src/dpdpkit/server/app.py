"""ASGI application served by the container image."""

from fastapi import FastAPI

from dpdpkit.server import __version__


def create_app() -> FastAPI:
    """Build the server application. Only the liveness probe exists so far; the API lands with SRV-02 onwards."""
    app = FastAPI(title="dpdpkit-server", version=__version__)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
