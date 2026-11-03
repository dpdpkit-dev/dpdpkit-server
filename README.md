# dpdpkit-server

Self-hosted [dpdpkit](https://github.com/dpdpkit-dev) server. It will run the dpdpkit REST API as a Docker image (`ghcr.io/dpdpkit-dev/server`), so apps in Node, PHP, Java or any other language get consent, notices, rights requests and retention over HTTP.

> **Disclaimer.** dpdpkit is software that helps you implement obligations under India's Digital Personal
> Data Protection Act, 2023 and the DPDP Rules, 2025. It does not provide legal advice and does not
> guarantee compliance. Decisions about notices, purposes, retention and incident reporting must be made
> by you or your counsel.

## Status

**Alpha.** Version 0.1.0a2 is the first working pre-release. APIs can still change between pre-releases.

The image is based on `dpdpkit-fastapi` and runs as non-root on a read-only file system:

```sh
docker run --read-only --tmpfs /tmp -p 8000:8000 ghcr.io/dpdpkit-dev/server
```

Configuration comes from environment variables or a mounted `dpdpkit.yaml` (environment wins):

```sh
docker run --read-only --tmpfs /tmp -p 8000:8000 \
  -v ./dpdpkit.yaml:/etc/dpdpkit/dpdpkit.yaml:ro \
  -e DPDPKIT_DATABASE_URL=postgresql://... ghcr.io/dpdpkit-dev/server
```

| Setting | Variable | `server:` key | Default |
|---|---|---|---|
| Config file | `DPDPKIT_CONFIG` | n/a | `/etc/dpdpkit/dpdpkit.yaml`, then `./dpdpkit.yaml`, if present |
| Bind address | `DPDPKIT_HOST` | `host` | `0.0.0.0` |
| Port | `DPDPKIT_PORT` | `port` | `8000` |
| Log level | `DPDPKIT_LOG_LEVEL` | `log_level` | `info` |
| Migrate on start | `DPDPKIT_MIGRATE_ON_STARTUP` | `migrate_on_startup` | `false` |
| Database URL (secret) | `DPDPKIT_DATABASE_URL` or `_FILE` | not allowed | none |
| Signing key (secret) | `DPDPKIT_SIGNING_KEY` or `_FILE` | not allowed | none |

The settings are loaded and validated at start-up.

Webhooks: `erasure.due` and `export.requested` are sent signed (`X-DPDPKit-Signature`) and retried with backoff.
After acting on its own data, your app confirms with the event `id` and the server records it in the ledger:

```sh
curl -X POST http://localhost:8000/v1/webhooks/confirmations -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"event_type": "export.requested", "event_id": "ev_...", "subject_id": "<request_id>", "status": "completed"}'
```

`subject_id` is the `schedule_id` (erasure.due) or `request_id` (export.requested) from the event data. A request
that is never confirmed stays open and shows as overdue. Failed deliveries are listed at
`GET /admin/webhooks/dead-letters` and can be re-queued with `POST /admin/webhooks/redeliver`.

Probes and metrics (no credentials, so keep them off the public internet): `/healthz` is liveness, `/readyz`
answers 503 until the database responds, and `/metrics` is Prometheus text (HTTP requests, worker job runs and last
success time, webhook deliveries by status).

The periodic jobs (retention, daily ledger verification, root-hash export, webhook delivery) run in a separate
container from the same image. Run exactly one:

```sh
docker run --read-only --tmpfs /tmp -p 8001:8000 -e DPDPKIT_DATABASE_URL=... ghcr.io/dpdpkit-dev/server worker
```

The worker serves the same `/healthz`, `/readyz` and `/metrics` on its port.

With Docker Compose (Postgres, the API and one worker; copy `.env.example` to `.env` and fill in the secrets first):

```sh
cp .env.example .env
docker compose up
```

It mounts `dpdpkit.example.yaml` as the config: edit the purposes, notice and `webhooks:` list for your app. Examples
of an app talking to the server: [`examples/node-express`](examples/node-express) (token minting, signed webhooks,
confirmations; has tests) and a [Laravel snippet](examples/laravel/README.md) for the same two jobs.

Images are published for `linux/amd64` and `linux/arm64` under one tag, signed with cosign (keyless, from the
release workflow) and carry an SBOM and build provenance. Verify before you run:

```sh
cosign verify ghcr.io/dpdpkit-dev/server:<version> \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github.com/dpdpkit-dev/dpdpkit-server/\.github/workflows/release-image\.yml@refs/tags/v'
```

With a database configured the server serves the consent and rights API under `/dpdp` (same contract as
`dpdpkit-fastapi`) and the admin dashboard at `/dpdp/admin/ui/`. Widgets call it with an end-user token from `POST /v1/tokens`; admins use the session from
`POST /admin/login`. The shared conformance suite runs against the app in the tests and against the built image in CI
(`DPDPKIT_CONFORMANCE=1` swaps the credentials for the suite's test headers; never set it outside tests).

Documentation:
https://dpdpkit-dev.github.io/dpdpkit-docs/dev/

## License

Apache-2.0. See [LICENSE](LICENSE). Contributions need a DCO sign-off; see [CONTRIBUTING.md](CONTRIBUTING.md).
