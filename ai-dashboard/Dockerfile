FROM node:22-bookworm-slim AS dependencies

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci


FROM node:22-bookworm-slim AS build

WORKDIR /app

ENV NODE_ENV=production

COPY --from=dependencies /app/node_modules ./node_modules
COPY . .

# Fix Windows line endings and executable permissions.
RUN find scripts -type f -name '*.sh' -exec sed -i 's/\r$//' {} + \
 && find scripts -type f -name '*.sh' -exec chmod 755 {} + \
 && npm run build


FROM node:22-bookworm-slim AS runtime

WORKDIR /app

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=4173

COPY --from=build /app /app

EXPOSE 4173

CMD ["npm", "run", "start"]
