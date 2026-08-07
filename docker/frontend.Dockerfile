# ── Intelligent Housekeeper 前端容器镜像 ──
FROM node:20-alpine AS build

WORKDIR /app

# 安装依赖(构建阶段需要 devDependencies 里的 vite, 不能 --only=production)
COPY frontend/package*.json ./
RUN npm ci && npm cache clean --force

# 复制前端源码并构建
COPY frontend/ .
RUN npm run build

# ── Nginx 运行阶段 ──
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
