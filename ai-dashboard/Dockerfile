FROM node:22-bookworm-slim

WORKDIR /app

COPY package.json package-lock.json ./

RUN npm ci --include=optional

COPY . .

# Normalize shell scripts copied from Windows/WSL.
RUN find scripts -type f -name '*.sh' -exec sed -i 's/\r$//' {} + \
 && find scripts -type f -name '*.sh' -exec chmod 755 {} +

ENV NODE_ENV=development
ENV HOST=0.0.0.0
ENV PORT=4173

EXPOSE 4173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "4173", "--strictPort"]
