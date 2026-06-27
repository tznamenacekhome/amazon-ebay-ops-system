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

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/scripts ./scripts

RUN addgroup -S nodejs && adduser -S nextjs -G nodejs \
  && chown -R nextjs:nodejs /app

USER nextjs
EXPOSE 3000
CMD ["npm", "start"]
