# syntax=docker/dockerfile:1.7
#   docker build -f infra/docker/web.Dockerfile -t pawguard-web .
FROM node:22.18.0-bookworm-slim AS build
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /src
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/ui/package.json packages/ui/package.json
COPY packages/api-client/package.json packages/api-client/package.json
COPY tests/package.json tests/package.json
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile --filter @pawguard/web...
COPY apps/web apps/web
COPY packages packages
RUN pnpm --filter @pawguard/web build

FROM node:22.18.0-bookworm-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN useradd --system --uid 10001 pawguard
WORKDIR /app
COPY --from=build --chown=pawguard /src/apps/web/.next/standalone ./
COPY --from=build --chown=pawguard /src/apps/web/.next/static ./apps/web/.next/static
USER pawguard
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
