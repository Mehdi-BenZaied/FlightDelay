# syntax=docker/dockerfile:1

# -----------------------------
# Stage 1: Install dependencies
# -----------------------------
FROM node:22-alpine AS dependencies

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci


# -----------------------------
# Stage 2: Build Vite frontend
# -----------------------------
FROM dependencies AS builder

WORKDIR /app

COPY . .

RUN npm run build


# -----------------------------
# Stage 3: Nginx runtime
# -----------------------------
FROM nginx:1.27-alpine AS runtime

RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]