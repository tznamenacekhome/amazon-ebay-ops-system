# syntax=docker/dockerfile:1

FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS builder
WORKDIR /app
ARG MBOP_BUILD_SHA=local
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_MBOP_BUILD_SHA=$MBOP_BUILD_SHA
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-alpine AS runner
WORKDIR /app
ARG MBOP_BUILD_SHA=local
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV MBOP_BUILD_SHA=$MBOP_BUILD_SHA
ENV NEXT_PUBLIC_MBOP_BUILD_SHA=$MBOP_BUILD_SHA

RUN addgroup -S nodejs && adduser -S nextjs -G nodejs

COPY --chown=nextjs:nodejs package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY --chown=nextjs:nodejs --from=builder /app/.next ./.next
COPY --chown=nextjs:nodejs --from=builder /app/public ./public
COPY --chown=nextjs:nodejs --from=builder /app/scripts ./scripts

USER nextjs
EXPOSE 3000
CMD ["npm", "start"]
