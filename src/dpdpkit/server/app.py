"""ASGI application served by the container image."""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from dpdpkit.fastapi import DPDPKit
from dpdpkit.server import __version__
from dpdpkit.server.engine import bind_auth, build_dpdpkit
from dpdpkit.server.metrics import Metrics
from dpdpkit.server.ops import router as ops_router
from dpdpkit.server.routes import router
from dpdpkit.server.settings import Settings
from dpdpkit.server.webhooks import router as webhooks_router


def create_app(
    settings: Settings | None = None, dpdpkit: DPDPKit | None = None, metrics: Metrics | None = None
) -> FastAPI:
    """Build the server application: probes and metrics (SRV-05), authentication (SRV-03) and webhook callbacks
    (SRV-04).

    ``settings`` default to the environment and the mounted ``dpdpkit.yaml`` (see :mod:`dpdpkit.server.settings`).
    ``dpdpkit`` is the engine the webhook endpoints write to; by default it is built from ``DPDPKIT_DATABASE_URL``,
    and without a database they answer 503. ``metrics`` is shared with the worker when it serves the same app.
    """
    app = FastAPI(title="dpdpkit-server", version=__version__)
    app.state.settings = settings = settings or Settings.load()
    app.state.dpdpkit = dpdpkit = dpdpkit or build_dpdpkit(settings)
    app.state.metrics = metrics or Metrics()
    if dpdpkit is not None:
        bind_auth(dpdpkit, settings)
        dpdpkit.install(app, prefix="/dpdp")

    @app.middleware("http")
    async def count_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        app.state.metrics.request(request.method, response.status_code)
        return response

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(ops_router)
    app.include_router(router)
    app.include_router(webhooks_router)

    return app
