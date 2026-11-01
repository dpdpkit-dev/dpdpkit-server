# dpdpkit-server

Self-hosted [dpdpkit](https://github.com/dpdpkit-dev) server. It will run the dpdpkit REST API as a Docker image (`ghcr.io/dpdpkit-dev/server`), so apps in Node, PHP, Java or any other language get consent, notices, rights requests and retention over HTTP.

> **Disclaimer.** dpdpkit is software that helps you implement obligations under India's Digital Personal
> Data Protection Act, 2023 and the DPDP Rules, 2025. It does not provide legal advice and does not
> guarantee compliance. Decisions about notices, purposes, retention and incident reporting must be made
> by you or your counsel.

## Status

**Not usable yet.** Version 0.0.1a0 is an empty pre-release that reserves the name on PyPI. The first working
release is planned for milestone v0.5 (planned for June 2027); the work is tracked as SRV-01 to SRV-09 in the dpdpkit task sheet.

Planned:

- Image based on `dpdpkit-fastapi` (non-root, read-only file system), multi-arch, signed with cosign
- Configuration from environment variables or a mounted `dpdpkit.yaml`
- Hashed API keys, signed end-user tokens, admin login with optional OIDC
- Webhooks (`erasure.due`, `export.requested`) with callback confirmation into the ledger
- `worker` command and `/healthz`, `/readyz`, `/metrics`

Until then, use [`dpdpkit-fastapi`](https://github.com/dpdpkit-dev/dpdpkit-fastapi) or the core library
[`dpdpkit-core`](https://github.com/dpdpkit-dev/dpdpkit-core). Documentation:
https://dpdpkit-dev.github.io/dpdpkit-docs/dev/

## License

Apache-2.0. See [LICENSE](LICENSE). Contributions need a DCO sign-off; see [CONTRIBUTING.md](CONTRIBUTING.md).
