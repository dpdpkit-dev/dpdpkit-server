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

## 0.0.1a0 - 2026-11-01

### Added
- Placeholder pre-release that reserves the package name on PyPI. It contains no functionality yet.
