"""ASGI application served by the container image."""

from fastapi import FastAPI

from dpdpkit.server import __version__
from dpdpkit.server.routes import router
from dpdpkit.server.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the server application. Only the liveness probe exists so far; the API lands with SRV-03 onwards.

    ``settings`` default to the environment and the mounted ``dpdpkit.yaml`` (see :mod:`dpdpkit.server.settings`).
    """
    app = FastAPI(title="dpdpkit-server", version=__version__)
    app.state.settings = settings or Settings.load()

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)

    return app
