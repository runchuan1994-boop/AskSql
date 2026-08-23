#!/usr/bin/env bash
# ============================================================
# NL2SQL Agent - 一键部署
# ============================================================
# 用法: ./run.sh
# 作用: 停止旧容器 → 构建 → 启动 → 健康检查 → 显示访问地址
# ============================================================

set -e

# 项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }

# 1. 检查 .env
if [ ! -f .env ]; then
    warn "未找到 .env 文件，从 .env.example 复制..."
    cp .env.example .env
    echo ""
    echo "请编辑 .env 填入你的 API Key 后重新运行。"
    exit 1
fi

# 2. 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "错误: 未安装 Docker"
    exit 1
fi

# 3. 停止旧容器（如果有）
echo ""
info "停止旧容器..."
docker compose down 2>/dev/null || true
ok "已清理旧容器"

# 4. 确保数据目录存在
mkdir -p backend/data backend/config/schemas backend/config/projects

# 5. 读取 .env 获取沙盒配置（用于判断是否需要构建沙盒镜像）
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# 6. 构建主服务镜像
echo ""
info "构建 Docker 镜像..."
docker compose build
ok "主服务镜像构建完成"

# 7. 构建沙盒镜像（如果启用了沙盒，或者镜像不存在）
SANDBOX_IMAGE="${SANDBOX_IMAGE:-nl2sql-sandbox:latest}"
if [ "${SANDBOX_ENABLED:-false}" = "true" ] || ! docker image inspect "$SANDBOX_IMAGE" &> /dev/null; then
    echo ""
    info "构建沙盒执行器镜像 ($SANDBOX_IMAGE)..."
    if [ -d backend/sandbox-image ]; then
        docker build -t "$SANDBOX_IMAGE" backend/sandbox-image/
        ok "沙盒镜像构建完成"
    else
        warn "未找到 backend/sandbox-image 目录，跳过沙盒镜像构建"
    fi
else
    info "沙盒镜像已存在且未启用沙盒，跳过构建"
fi

# 8. 启动服务
echo ""
info "启动服务..."
docker compose up -d
ok "容器已启动"

# 9. 等待后端就绪
echo ""
info "等待后端服务就绪..."
max_wait=60
waited=0
while [ $waited -lt $max_wait ]; do
    if curl -sf http://localhost:8000/health &> /dev/null; then
        ok "后端服务就绪（等待了 ${waited}s）"
        break
    fi
    sleep 2
    waited=$((waited + 2))
    echo -n "."
done
echo ""

if [ $waited -ge $max_wait ]; then
    warn "后端启动超时，请检查日志: docker compose logs backend"
fi

# 10. 沙盒运行时提示
if [ "${SANDBOX_ENABLED:-false}" = "true" ]; then
    echo ""
    info "沙盒已启用，运行时: ${SANDBOX_RUNTIME:-runc}"
    if [ "${SANDBOX_RUNTIME:-runc}" = "runsc" ]; then
        ok "gVisor (runsc) 运行时：内核级隔离"
    else
        warn "runc 运行时：普通容器隔离（生产环境建议使用 gVisor）"
    fi
fi

# 11. 完成
echo ""
echo -e "${BOLD}${GREEN}  NL2SQL Agent 部署成功！${NC}"
echo ""
echo -e "  前端地址:  http://localhost:5173"
echo -e "  后端 API:  http://localhost:8000"
echo -e "  API 文档:  http://localhost:8000/docs"
echo ""
echo -e "  查看日志:  docker compose logs -f"
echo -e "  停止服务:  docker compose down"
echo ""
