#!/usr/bin/env bash
# ============================================================
# Langfuse 可观测性 — 一键部署脚本
# ============================================================
# 用法: ./scripts/setup-langfuse.sh
# 作用: 启动 Langfuse → 初始化管理员/项目/API Key → 写入 .env
# 完成后运行 ./run.sh 启动主服务
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }

echo ""
echo -e "${BOLD}🔍 Langfuse 可观测性部署${NC}"
echo ""

# 1. 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "错误: 未安装 Docker"
    exit 1
fi
ok "Docker 已安装"

# 2. 检查 .env
if [ ! -f .env ]; then
    warn "未找到 .env 文件，从 .env.example 复制..."
    cp .env.example .env
fi

# 3. 读取 .env
set -a
# shellcheck disable=SC1091
source .env
set +a

LANGFUSE_HOST="${LANGFUSE_HOST:-http://localhost:3030}"
ADMIN_EMAIL="${LANGFUSE_ADMIN_EMAIL:-admin@nl2sql.local}"
ADMIN_PASSWORD="${LANGFUSE_ADMIN_PASSWORD:-admin123456}"
ADMIN_NAME="${LANGFUSE_ADMIN_NAME:-NL2SQL Admin}"
PROJECT_NAME="${LANGFUSE_PROJECT_NAME:-NL2SQL}"

# 4. 检查 Langfuse 是否已经在运行
echo ""
info "检查 Langfuse 状态..."
if docker compose ps --format '{{.Service}} {{.State}}' 2>/dev/null | grep -q '^langfuse running$'; then
    ok "Langfuse 已在运行"
else
    info "启动 Langfuse 服务..."
    docker compose up -d langfuse
    ok "Langfuse 容器已启动"
fi

# 5. 等待 Langfuse 就绪
echo ""
info "等待 Langfuse 服务就绪（首次启动可能需要 1-2 分钟）..."
langfuse_wait=0
langfuse_max=180
while [ $langfuse_wait -lt $langfuse_max ]; do
    if curl -sf "$LANGFUSE_HOST/api/public/health" &> /dev/null; then
        ok "Langfuse 就绪（等待了 ${langfuse_wait}s）"
        break
    fi
    sleep 3
    langfuse_wait=$((langfuse_wait + 3))
    echo -n "."
done
echo ""

if [ $langfuse_wait -ge $langfuse_max ]; then
    warn "Langfuse 启动超时，请检查日志: docker compose logs langfuse"
    echo ""
    echo "稍后可以重新运行此脚本继续初始化"
    exit 1
fi

# 6. 检查是否已配置 API Key
if grep -q '^LANGFUSE_PUBLIC_KEY=.\+' .env; then
    ok "Langfuse API Key 已配置，跳过初始化"
    echo ""
    echo -e "${BOLD}${GREEN}  Langfuse 已就绪！${NC}"
    echo ""
    echo -e "  UI 地址:  $LANGFUSE_HOST"
    echo -e "  管理员:  $ADMIN_EMAIL"
    echo -e "  项目:    $PROJECT_NAME"
    echo ""
    echo -e "  下一步:  ./run.sh  启动主服务"
    echo ""
    exit 0
fi

# 7. 自动初始化
echo ""
info "自动初始化 Langfuse..."

if [ -x "$SCRIPT_DIR/langfuse-init.sh" ]; then
    LANGFUSE_HOST="$LANGFUSE_HOST" \
    LANGFUSE_ADMIN_EMAIL="$ADMIN_EMAIL" \
    LANGFUSE_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    LANGFUSE_ADMIN_NAME="$ADMIN_NAME" \
    LANGFUSE_PROJECT_NAME="$PROJECT_NAME" \
    "$SCRIPT_DIR/langfuse-init.sh" || warn "自动初始化未完全成功"
else
    warn "未找到 langfuse-init.sh 脚本"
fi

# 8. 最终检查
if grep -q '^LANGFUSE_PUBLIC_KEY=.\+' .env; then
    echo ""
    echo -e "${BOLD}${GREEN}  ✅ Langfuse 部署完成！${NC}"
    echo ""
    echo -e "  UI 地址:  $LANGFUSE_HOST"
    echo -e "  管理员:  $ADMIN_EMAIL / $ADMIN_PASSWORD"
    echo -e "  项目:    $PROJECT_NAME"
    echo -e "  API Key: 已自动写入 .env"
    echo ""
    echo -e "  下一步:  ./run.sh  启动主服务"
    echo ""
    echo -e "  ${YELLOW}⚠️  生产环境请及时修改默认密码！${NC}"
    echo ""
else
    echo ""
    warn "API Key 未自动配置，请手动操作："
    echo ""
    echo "  1. 访问 $LANGFUSE_HOST"
    echo "  2. 登录: $ADMIN_EMAIL / $ADMIN_PASSWORD"
    echo "  3. 进入项目 Settings → API Keys → Create API Key"
    echo "  4. 将 Public Key 和 Secret Key 填入 .env"
    echo ""
    echo "  配置完成后运行 ./run.sh 启动主服务"
    echo ""
fi
