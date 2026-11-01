# Changelog

All code packages in the dpdpkit release train share one version number. This package joins the train with its
first working release.

## Unreleased

### Added
- Container image `ghcr.io/dpdpkit-dev/server` built from `dpdpkit-fastapi`: non-root (UID 10001), runs with a
  read-only file system, `/healthz` liveness probe. Multi-arch, cosign-signed, released by `release-image.yml`.
- `python -m dpdpkit.server` entry point (`DPDPKIT_HOST`, `DPDPKIT_PORT`).

## 0.0.1a0 - 2026-11-01

### Added
- Placeholder pre-release that reserves the package name on PyPI. It contains no functionality yet.
