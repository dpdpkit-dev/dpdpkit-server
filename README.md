# dpdpkit-server

Self-hosted [dpdpkit](https://github.com/dpdpkit-dev) server. It will run the dpdpkit REST API as a Docker image (`ghcr.io/dpdpkit-dev/server`), so apps in Node, PHP, Java or any other language get consent, notices, rights requests and retention over HTTP.

> **Disclaimer.** dpdpkit is software that helps you implement obligations under India's Digital Personal
> Data Protection Act, 2023 and the DPDP Rules, 2025. It does not provide legal advice and does not
> guarantee compliance. Decisions about notices, purposes, retention and incident reporting must be made
> by you or your counsel.

## Status

**Not usable yet.** Version 0.0.1a0 is an empty pre-release that reserves the name on PyPI. The first working
release is planned for milestone v0.5 (planned for June 2027); the work is tracked as SRV-01 to SRV-09 in the dpdpkit task sheet.

Done so far: the `Dockerfile` (based on `dpdpkit-fastapi`, non-root, runs with a read-only file system) and the
image release workflow (multi-arch, signed with cosign). The image only serves `/healthz` for now:

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

The settings are loaded and validated at start-up; they are not wired to the database or the API yet.

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

Until then, use [`dpdpkit-fastapi`](https://github.com/dpdpkit-dev/dpdpkit-fastapi) or the core library
[`dpdpkit-core`](https://github.com/dpdpkit-dev/dpdpkit-core). Documentation:
https://dpdpkit-dev.github.io/dpdpkit-docs/dev/

## License

Apache-2.0. See [LICENSE](LICENSE). Contributions need a DCO sign-off; see [CONTRIBUTING.md](CONTRIBUTING.md).
