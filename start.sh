#!/usr/bin/env bash
# ============================================================
# Mawork 一键启动脚本（WSL2）
#   启动：./start.sh
#   停止：Ctrl + C
# ============================================================
set -uo pipefail

# ---------------- 配置区（按需修改）----------------
CONDA_HOME="${HOME}/miniforge3"        # conda 安装目录
CONDA_ENV="py312torch222"              # conda 环境名
NVM_DIR="${HOME}/.nvm"                 # nvm 目录
NODE_VERSION="v22.23.1"                # Node 版本
PROJECT_ROOT="/mnt/d/Desktop/Project_Group/Mawork"
BACKEND_PORT=8001
FRONTEND_PORT=5174
ENABLE_RELOAD=true                     # 后端热重载（/mnt 挂载下若失效改 false）
# --------------------------------------------------

GREEN='\033[0;32m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'
RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'
log()  { echo -e "${GREEN}[Mawork]${NC} $1"; }
warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
err()  { echo -e "${RED}[错误]${NC} $1"; exit 1; }

# ---------- 1. 加载 conda（脚本非交互，必须手动 source）----------
[ -f "$CONDA_HOME/etc/profile.d/conda.sh" ] || err "找不到 conda：$CONDA_HOME"
source "$CONDA_HOME/etc/profile.d/conda.sh"
conda activate "$CONDA_ENV" || err "conda 环境不存在：$CONDA_ENV"
log "conda 已激活 → ${BOLD}$CONDA_ENV${NC} ($(python -V 2>&1 | awk '{print $2}'))"

# ---------- 2. 加载 Node（nvm 同样需手动 source）----------
export NVM_DIR
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh" >/dev/null 2>&1
nvm use "$NODE_VERSION" >/dev/null 2>&1
# 兜底：nvm 未生效则直接用绝对路径
command -v npm >/dev/null 2>&1 || export PATH="$NVM_DIR/versions/node/$NODE_VERSION/bin:$PATH"
command -v npm >/dev/null 2>&1 || err "找不到 npm，请检查 nvm 安装"
log "Node 已就绪 → ${BOLD}$(node -v)${NC} / npm $(npm -v)"

# ---------- 3. 释放被占用的端口 ----------
free_port() {
    local port=$1 pids
    pids=$(ss -tlnp "sport = :$port" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | sort -u)
    if [ -n "$pids" ]; then
        warn "端口 $port 被占用，正在释放..."
        for p in $pids; do kill -9 "$p" 2>/dev/null; done
        sleep 1
    fi
}
free_port "$BACKEND_PORT"
free_port "$FRONTEND_PORT"

# ---------- 4. 依赖与目录检查 ----------
cd "$PROJECT_ROOT" || err "项目目录不存在：$PROJECT_ROOT"

# 载入 .env（与 Docker 部署共用同一套凭证/配置）；不存在则跳过
if [ -f "$PROJECT_ROOT/.env" ]; then
  set -a
  . "$PROJECT_ROOT/.env"
  set +a
  log ".env 已载入（本地与 Docker 共用凭证）"
fi

python -c "import fastapi, uvicorn" >/dev/null 2>&1 || {
    warn "缺少后端依赖，正在安装 requirements.txt ..."
    pip install -r backend/requirements.txt || err "依赖安装失败"
}
[ -d node_modules ] || [ -d "$PROJECT_ROOT/../node_modules" ] || warn "未检测到 node_modules，前端可能启动失败"
mkdir -p "$PROJECT_ROOT/workspaces"   # resources 路由依赖该目录，缺失会 404

# ---------- 5. 启动后端 ----------
log "启动后端 FastAPI → 端口 $BACKEND_PORT"
RELOAD_FLAG=""; $ENABLE_RELOAD && RELOAD_FLAG="--reload"
uvicorn backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" $RELOAD_FLAG \
    > >(sed "s/^/${CYAN}[后端]${NC} /") 2>&1 &
BACKEND_PID=$!

# 等待后端健康检查通过
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
        log "后端就绪 ✓"; break
    fi
    [ "$i" -eq 30 ] && warn "后端健康检查超时，请查看下方日志"
    sleep 1
done

# ---------- 6. 启动前端 ----------
log "启动前端 Vite → 端口 $FRONTEND_PORT"
cd "$PROJECT_ROOT/frontend" || err "前端目录不存在"
npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" \
    > >(sed "s/^/${GREEN}[前端]${NC} /") 2>&1 &
FRONTEND_PID=$!

# ---------- 7. 退出清理 ----------
cleanup() {
    echo ""
    log "正在停止服务..."
    pkill -P "$BACKEND_PID"  2>/dev/null   # 先杀 --reload 派生的子进程
    pkill -P "$FRONTEND_PID" 2>/dev/null
    kill "$BACKEND_PID"  "$FRONTEND_PID" 2>/dev/null
    sleep 1
    log "已停止 ✓"
    exit 0
}
trap cleanup INT TERM

# ---------- 8. 启动完成 ----------
sleep 3
echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Mawork 已启动${NC}"
echo -e "  前端  →  http://localhost:$FRONTEND_PORT"
echo -e "  后端  →  http://localhost:$BACKEND_PORT   (API 文档 /docs)"
echo -e "  停止  →  ${YELLOW}Ctrl + C${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""

wait
