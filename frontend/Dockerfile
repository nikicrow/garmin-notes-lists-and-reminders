FROM node:24-alpine AS builder

WORKDIR /build
RUN corepack enable

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm build

FROM nginx:alpine

COPY docker/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=5s \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:80/ || exit 1
