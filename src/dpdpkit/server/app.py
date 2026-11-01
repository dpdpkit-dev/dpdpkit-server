"""ASGI application served by the container image."""

from fastapi import FastAPI

from dpdpkit.fastapi import DPDPKit
from dpdpkit.server import __version__
from dpdpkit.server.routes import router
from dpdpkit.server.settings import Settings
from dpdpkit.server.webhooks import router as webhooks_router


def create_app(settings: Settings | None = None, dpdpkit: DPDPKit | None = None) -> FastAPI:
    """Build the server application: liveness probe, authentication (SRV-03) and webhook callbacks (SRV-04).

    ``settings`` default to the environment and the mounted ``dpdpkit.yaml`` (see :mod:`dpdpkit.server.settings`).
    ``dpdpkit`` is the engine the webhook endpoints write to; without it they answer 503.
    """
    app = FastAPI(title="dpdpkit-server", version=__version__)
    app.state.settings = settings or Settings.load()
    app.state.dpdpkit = dpdpkit

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    app.include_router(webhooks_router)

    return app
