"""The server application as the conformance suite sees it: DPDPKIT_ASGI_APP=app:app, run from this directory."""

from dpdpkit.server.app import create_app

app = create_app()
