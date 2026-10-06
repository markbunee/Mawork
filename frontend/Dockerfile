# MaWork 前端镜像（多阶段：node 构建 -> nginx 托管静态产物并反代 /api）
# 构建（在 Mawork/frontend 目录执行）：
#   docker build -t mawork-frontend .

# ---- 阶段 1：构建 ----
FROM node:22-bookworm-slim AS build
WORKDIR /app

# 使用国内 npm 镜像，加快依赖下载（服务器在国内时必需）
RUN npm config set registry https://registry.npmmirror.com

# 限制 node 堆内存，避免在低配服务器（如 2核2G）构建时 OOM 把容器打崩。
ENV NODE_OPTIONS=--max-old-space-size=768

COPY package.json ./
RUN npm install
COPY . .
# 跳过 vue-tsc 类型检查（类型检查在本地/CI 完成），仅做 Vite 打包以省内存。
# 若仍担心服务器构建 OOM，可改为在本地跑 `npm run build` 后把 dist/ 拷到服务器，
# 再用只拷贝 dist 的 nginx 镜像部署（无需在服务器上跑 node 工具链）。
RUN npm run build-only

# ---- 阶段 2：运行 ----
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
