# MaWork 后端镜像
# 构建（在 Mawork/ 根目录执行，构建上下文为根，便于把 backend 作为包导入）：
#   docker build -f backend/Dockerfile -t mawork-backend .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 先装依赖（利用层缓存）；使用清华 PyPI 镜像加速
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir -r backend/requirements.txt

# 再拷源码
COPY backend/ ./backend/

EXPOSE 8001

# 必须在 /app 下，使 backend 作为包被导入
# 单 worker 保内存；limit-max-requests 定期回收 worker 防内存泄漏累积；
# timeout-keep-alive 释放空闲连接；backlog 控制排队上限。并发/内存硬保护由
# 应用层 guard 中间件负责（运行时按系统资源自适应）。
#
# ⚠️ --proxy-headers + --forwarded-allow-ips 必须加：
# 登录限流用 request.client.host 作为桶键，而 uvicorn 默认只信任 127.0.0.1
# 发来的 X-Forwarded-For。前端 nginx 跑在 webnet 容器网段（另一网段），
# 不加这两个参数时 XFF 会被丢弃 → 所有请求的 client.host 相同 →
# 限流退化成「全站共用一个桶」，任何人打满 5 次/min 会让全员 1 分钟登不进去。
# 放行 * 是安全的：backend 只经由内部 webnet 暴露（expose，不映射宿主端口），
# 公网流量必须先过 nginx，不存在被直连伪造 XFF 的路径。
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port 8001 --workers 1 --limit-max-requests 2000 --timeout-keep-alive 20 --backlog 128 --proxy-headers --forwarded-allow-ips='*'"]
