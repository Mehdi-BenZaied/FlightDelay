# syntax=docker/dockerfile:1

# ------------------------------------------------------------
# Dependencies
# ------------------------------------------------------------
FROM node:22-alpine AS dependencies

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci \
    --no-audit \
    --no-fund


# ------------------------------------------------------------
# Frontend build
# ------------------------------------------------------------
FROM dependencies AS builder

WORKDIR /app

COPY . .

RUN npm run build

# Fail immediately when Vite did not create the expected files.
RUN test -d /app/dist \
    && test -f /app/dist/index.html


# ------------------------------------------------------------
# Nginx runtime
# ------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

RUN rm -f /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist/ /usr/share/nginx/html/

RUN test -f /usr/share/nginx/html/index.html \
    && nginx -t

EXPOSE 80

HEALTHCHECK \
    --interval=10s \
    --timeout=5s \
    --start-period=15s \
    --retries=12 \
    CMD wget \
        --quiet \
        --tries=1 \
        --output-document=/dev/null \
        http://127.0.0.1/health \
        || exit 1

CMD ["nginx", "-g", "daemon off;"]