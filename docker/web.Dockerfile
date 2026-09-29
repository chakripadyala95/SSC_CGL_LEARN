FROM node:22-slim AS build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web .
RUN npm run build

FROM node:22-slim
WORKDIR /web
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /web/.next/standalone ./
COPY --from=build /web/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
