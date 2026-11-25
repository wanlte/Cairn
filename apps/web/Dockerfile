# Cairn Web 生产镜像：Node 构建静态产物，Nginx 托管并作为统一反向代理入口
# Node 版本与本地开发环境保持一致（构建产物已在 Node 24 下验证）
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# 国内构建走 npmmirror；若 lockfile 解析仍指向 npmjs 导致慢，可临时改用 npm install
RUN npm ci --registry=https://registry.npmmirror.com
COPY . .
RUN npm run build

FROM nginx:stable-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
