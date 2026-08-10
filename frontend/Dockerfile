FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines VITE_* at build time, so the backend URL has to be known here —
# it cannot be injected when the container starts.
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

EXPOSE 7205

CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "7205"]
