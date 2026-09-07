# AEGIS frontend — build the existing Vite app, serve the static output with nginx.
# Build context is the repo root:  docker build -f frontend/Dockerfile .

# --- build stage ---
FROM node:22-alpine AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# API/WS endpoints are baked in at build time (Vite inlines VITE_* vars).
ARG VITE_API_URL=http://localhost:8000
ARG VITE_WS_URL=ws://localhost:8000/ws
ENV VITE_API_URL=$VITE_API_URL \
    VITE_WS_URL=$VITE_WS_URL

RUN npm run build

# --- serve stage ---
FROM nginx:alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
