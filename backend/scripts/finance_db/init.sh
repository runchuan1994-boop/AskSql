#!/usr/bin/env bash
# ============================================================
# 金融测试数据库一键初始化脚本
# 功能：启动 PostgreSQL → 建表 → 生成数据 → 验证
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-finance_db}"
DB_USER="${DB_USER:-nl2sql}"
DB_PASSWORD="${DB_PASSWORD:-nl2sql123}"

echo "=============================================="
echo "  金融测试数据库初始化"
echo "=============================================="
echo ""

# ------------------------------------------------------------
# 步骤 1: 检查 Docker 和 docker compose
# ------------------------------------------------------------
echo "[1/5] 检查环境..."

if ! command -v docker &> /dev/null; then
    echo "  ❌ 未找到 docker，请先安装 Docker Desktop"
    exit 1
fi

# 兼容 docker-compose 和 docker compose
if docker compose version &> /dev/null; then
    DC="docker compose"
elif command -v docker-compose &> /dev/null; then
    DC="docker-compose"
else
    echo "  ❌ 未找到 docker compose，请先安装"
    exit 1
fi
echo "  ✓ Docker: $(docker --version)"
echo "  ✓ Compose: $($DC version --short 2>/dev/null || echo 'ok')"

# ------------------------------------------------------------
# 步骤 2: 启动 PostgreSQL
# ------------------------------------------------------------
echo ""
echo "[2/5] 启动 PostgreSQL..."

cd "$PROJECT_ROOT"
$DC up -d postgres

echo "  等待 PostgreSQL 就绪..."
MAX_RETRIES=30
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if $DC exec -T postgres pg_isready -U "$DB_USER" -d "$DB_NAME" &> /dev/null; then
        echo "  ✓ PostgreSQL 已就绪"
        break
    fi
    RETRY=$((RETRY + 1))
    sleep 2
done

if [ $RETRY -eq $MAX_RETRIES ]; then
    echo "  ❌ PostgreSQL 启动超时"
    exit 1
fi

# ------------------------------------------------------------
# 步骤 3: 执行 schema
# ------------------------------------------------------------
echo ""
echo "[3/5] 创建数据库表结构..."

$DC exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" < "$SCRIPT_DIR/schema.sql" > /dev/null
echo "  ✓ 表结构创建完成"

# ------------------------------------------------------------
# 步骤 4: 安装 Python 依赖并生成数据
# ------------------------------------------------------------
echo ""
echo "[4/5] 生成模拟数据..."

# 检查 Python 和必要包
if ! python3 -c "import faker, psycopg2" 2>/dev/null; then
    echo "  安装依赖 (Faker, psycopg2-binary)..."
    pip install --quiet Faker psycopg2-binary 2>/dev/null || pip3 install --quiet Faker psycopg2-binary
fi

DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_NAME="$DB_NAME" \
DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" \
python3 "$SCRIPT_DIR/generate_data.py"

# ------------------------------------------------------------
# 步骤 5: 完成信息
# ------------------------------------------------------------
echo ""
echo "=============================================="
echo "  ✅ 初始化完成！"
echo "=============================================="
echo ""
echo "  连接信息："
echo "    主机:     $DB_HOST:$DB_PORT"
echo "    数据库:   $DB_NAME"
echo "    用户:     $DB_USER"
echo "    密码:     $DB_PASSWORD"
echo "    URL:      postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
echo ""
echo "  连接命令："
echo "    $DC exec -it postgres psql -U $DB_USER -d $DB_NAME"
echo ""
echo "  停止数据库："
echo "    $DC stop postgres"
echo ""
echo "  删除数据库（清空数据）："
echo "    $DC down -v postgres"
echo ""
