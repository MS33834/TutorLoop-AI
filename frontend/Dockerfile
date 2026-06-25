# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# VITE_* variables are read at build time, so accept them as build args and
# expose them as ENV so `npm run build` can inline them into the bundle.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Substitute the API base URL into the nginx config at build time. This avoids
# relying on runtime envsubst inside the non-root nginx-unprivileged image,
# where /etc/nginx/conf.d may not be writable.
RUN apk add --no-cache gettext
COPY default.conf.template ./
RUN envsubst '$VITE_API_BASE_URL' < default.conf.template > default.conf

# Runtime stage: nginx-unprivileged runs as a non-root user (uid 101) and
# listens on 8080 by default, so the container does not run as root.
FROM nginxinc/nginx-unprivileged:1.25-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY --from=builder /app/default.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
