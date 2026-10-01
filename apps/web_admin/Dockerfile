# syntax=docker/dockerfile:1.7
# Multi-stage Dockerfile for `apps/web_admin` (Parkos Admin PWA) — HU-F13.7.
#
# BR1: static `vite build` output served by a lightweight Nginx image —
# build on `node:20-alpine`, serve on `nginx:${NGINX_VERSION}` — coherent
# with web_admin being a client-only PWA (no SSR).
#
# Build context MUST be the pnpm workspace root (`apps/`), NOT
# `apps/web_admin/`: `pnpm install --frozen-lockfile` resolves
# `@parkos/ui-kit` via `workspace:*` (see `apps/pnpm-workspace.yaml`,
# lockfile `apps/pnpm-lock.yaml`) and pnpm needs every workspace member's
# manifest on disk to validate that lockfile — including
# `electron-sucursal`, even though this image never builds it. A context
# scoped to `apps/web_admin/` alone fails with `ERR_PNPM_NO_IMPORTER_MANIFEST_FOUND`
# / an `EUNSUPPORTEDPROTOCOL` on the `workspace:*` specifier.
#
#   docker build -f apps/web_admin/Dockerfile -t parkos-web-admin:smoke apps/
#
# Run + smoke test (BR1 validation — HTTP healthcheck, `GET /` -> 200):
#   docker run --rm -d -p 8080:80 --name web-admin-smoke parkos-web-admin:smoke
#   curl -fsS http://localhost:8080/
#   docker stop web-admin-smoke
#
# BR3: no `VITE_API_BASE_URL` (or any `import.meta.env.VITE_*`) exists in
# web_admin's source — every API call is a relative `/api/...` path,
# proxied by Vite in dev (`vite.config.ts` -> `server.proxy['/api']`) and
# by this image's `nginx.conf` in prod (BR2). See `.env.example` for the
# build-time ARGs this image actually reads.

ARG NODE_VERSION=20-alpine
ARG NGINX_VERSION=1.27-alpine

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM node:${NODE_VERSION} AS builder

WORKDIR /workspace

# Workspace manifests first (rarely change) — maximizes layer cache reuse
# across builds that only touch application source.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY ui-kit/package.json ./ui-kit/package.json
COPY web_admin/package.json ./web_admin/package.json
COPY electron-sucursal/package.json ./electron-sucursal/package.json

# `--filter web_admin...` installs web_admin + the workspace packages it
# depends on (`@parkos/ui-kit`) only — `electron-sucursal`'s manifest is
# still on disk (above) so `--frozen-lockfile` can validate the whole
# workspace, but its (much heavier, Electron-specific) deps never get
# installed into this image.
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    corepack enable \
    && pnpm install --frozen-lockfile --filter web_admin...

# Application source (changes often) — copied last for cache reuse.
# `ui-kit` is source-only (`main: src/index.ts`, no build step of its own;
# see apps/ui-kit/package.json) — web_admin's own build compiles it in
# place through the pnpm workspace symlink.
COPY ui-kit ./ui-kit
COPY web_admin ./web_admin

WORKDIR /workspace/web_admin
RUN pnpm run build

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM nginx:${NGINX_VERSION} AS runtime

ARG BUILD_VERSION=dev
LABEL org.opencontainers.image.title="parkos-web-admin" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.source="https://github.com/sgveasypunto-ia/PArkOS" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.base.name="nginx:${NGINX_VERSION}"

COPY --from=builder /workspace/web_admin/dist /usr/share/nginx/html
COPY web_admin/nginx.conf /etc/nginx/conf.d/default.conf

# No explicit `USER` override here: the stock `nginx:alpine` image already
# runs its worker processes (the ones that actually serve requests) as the
# built-in low-privilege `nginx` user via `/etc/nginx/nginx.conf`'s
# `user nginx;` directive, which this Dockerfile does not touch. The
# master process briefly needs root only to bind the privileged port 80
# below — this image is smoke-tested with `-p <host-port>:80` (BR1/BR2).
# Forcing a custom non-root `USER` at the image level would break that
# bind without also granting `CAP_NET_BIND_SERVICE`.
EXPOSE 80

# BR1 validation target: `GET /` -> 200. `wget` (BusyBox) ships in the
# base `alpine` image `nginx:alpine` is built from; `curl` does not.
# `127.0.0.1`, not `localhost`: our `nginx.conf` (replacing the image's
# default) only `listen`s on IPv4 — the image's own
# `10-listen-on-ipv6-by-default.sh` entrypoint script only adds
# `listen [::]:80` when `default.conf`'s checksum still matches the
# packaged original, which ours deliberately does not. Inside the
# container `localhost` resolves `::1` first, so `wget` would hit
# "connection refused" on a port nothing listens on and the container
# would never report healthy despite serving real IPv4 traffic fine.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
