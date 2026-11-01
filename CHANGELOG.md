# Changelog

All code packages in the dpdpkit release train share one version number. This package joins the train with its
first working release.

## Unreleased

### Added
- Container image `ghcr.io/dpdpkit-dev/server` built from `dpdpkit-fastapi`: non-root (UID 10001), runs with a
  read-only file system, `/healthz` liveness probe. Multi-arch, cosign-signed, released by `release-image.yml`.
- `python -m dpdpkit.server` entry point.
- Configuration from environment variables (`DPDPKIT_HOST`, `DPDPKIT_PORT`, `DPDPKIT_LOG_LEVEL`,
  `DPDPKIT_MIGRATE_ON_STARTUP`, `DPDPKIT_DATABASE_URL`, `DPDPKIT_SIGNING_KEY`) or a mounted `dpdpkit.yaml`
  (`DPDPKIT_CONFIG`, else `/etc/dpdpkit/dpdpkit.yaml` or `./dpdpkit.yaml`) with a `server:` section.
  Environment wins over the file. Secrets come from the environment or `*_FILE` variables, never from the YAML.
  Invalid settings stop start-up with a clear message.
- Authentication (`dpdpkit.server.auth`, `dpdpkit.server.routes`):
  - API keys for backends, stored only as SHA-256 hashes (`DPDPKIT_API_KEY_HASHES` or `server.api_key_hashes`).
    `python -m dpdpkit.server new-api-key` prints a key once, with its hash.
  - `POST /v1/tokens` mints short-lived HMAC-signed end-user tokens for widgets (needs an API key and
    `DPDPKIT_SIGNING_KEY`). Token types are key-separated, so a user token never works as an admin session.
  - Admin login: `POST /admin/login` with a scrypt-hashed password (`DPDPKIT_ADMIN_PASSWORD_HASH`, made with
    `python -m dpdpkit.server hash-password`) and optional OIDC (`/admin/oidc/login` and `/callback`; settings
    `oidc_issuer`, `oidc_client_id`, `oidc_redirect_uri`, `DPDPKIT_OIDC_CLIENT_SECRET`, `admin_emails`).
  - `require_api_key`, `require_user_token` and `require_admin` dependencies for the endpoints that follow.

## 0.0.1a0 - 2026-11-01

### Added
- Placeholder pre-release that reserves the package name on PyPI. It contains no functionality yet.
