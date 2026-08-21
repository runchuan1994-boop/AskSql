# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

COPY package*.json ./
# 使用淘宝 npm 镜像加速
RUN npm config set registry https://registry.npmmirror.com && npm ci

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# 支持 SPA 路由
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
