#!/usr/bin/env bash
# ============================================================
# Langfuse 自动初始化脚本
# ============================================================
# 作用: 自动创建管理员用户、默认项目、API Key，并写入 .env
# 用法: ./scripts/langfuse-init.sh （由 run.sh 自动调用）
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }

LANGFUSE_HOST="${LANGFUSE_HOST:-http://localhost:3030}"
ADMIN_EMAIL="${LANGFUSE_ADMIN_EMAIL:-admin@nl2sql.local}"
ADMIN_PASSWORD="${LANGFUSE_ADMIN_PASSWORD:-admin123456}"
ADMIN_NAME="${LANGFUSE_ADMIN_NAME:-NL2SQL Admin}"
PROJECT_NAME="${LANGFUSE_PROJECT_NAME:-NL2SQL}"

# 如果 .env 中已经配置了 key，跳过
if [ -f .env ] && grep -q '^LANGFUSE_PUBLIC_KEY=.\+' .env; then
    info "Langfuse API Key 已配置，跳过自动初始化"
    exit 0
fi

info "Langfuse 自动初始化..."
info "  地址: $LANGFUSE_HOST"
info "  管理员: $ADMIN_EMAIL"

# ------------------------------------------------------------
# Step 1: 创建初始管理员用户
# ------------------------------------------------------------
info "创建管理员用户..."

# 先尝试直接登录（可能已经创建过了）
LOGIN_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$LANGFUSE_HOST/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" 2>/dev/null || echo "")

LOGIN_CODE=$(echo "$LOGIN_RESPONSE" | tail -1)
LOGIN_BODY=$(echo "$LOGIN_RESPONSE" | sed '$d')

if [ "$LOGIN_CODE" = "200" ] || [ "$LOGIN_CODE" = "201" ]; then
    ok "管理员已存在，登录成功"
    ACCESS_TOKEN=$(echo "$LOGIN_BODY" | grep -o '"accessToken":"[^"]*"' | cut -d'"' -f4)

    if [ -z "$ACCESS_TOKEN" ]; then
        # 尝试从 cookie 中获取（不同版本返回方式不同）
        warn "未找到 accessToken，尝试 cookie 方式..."
        # 尝试另一种方式：从 response body 提取 token
        ACCESS_TOKEN=$(echo "$LOGIN_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token') or d.get('token') or d.get('accessToken',''))" 2>/dev/null || echo "")
    fi
else
    # 登录失败，尝试用 signup 接口创建
    info "创建新管理员账号..."
    SIGNUP_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$LANGFUSE_HOST/api/auth/signup" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\",\"name\":\"$ADMIN_NAME\"}" 2>/dev/null || echo "")

    SIGNUP_CODE=$(echo "$SIGNUP_RESPONSE" | tail -1)
    SIGNUP_BODY=$(echo "$SIGNUP_RESPONSE" | sed '$d')

    if [ "$SIGNUP_CODE" = "200" ] || [ "$SIGNUP_CODE" = "201" ]; then
        ok "管理员创建成功"
        ACCESS_TOKEN=$(echo "$SIGNUP_BODY" | grep -o '"accessToken":"[^"]*"' | cut -d'"' -f4)
        if [ -z "$ACCESS_TOKEN" ]; then
            ACCESS_TOKEN=$(echo "$SIGNUP_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token') or d.get('token') or d.get('accessToken',''))" 2>/dev/null || echo "")
        fi
    else
        warn "创建管理员失败 (HTTP $SIGNUP_CODE): $SIGNUP_BODY"
        warn "跳过自动初始化，请手动在 Langfuse UI 中创建 API Key"
        exit 0
    fi
fi

if [ -z "$ACCESS_TOKEN" ]; then
    warn "无法获取访问令牌，请手动在 Langfuse UI 中创建 API Key"
    exit 0
fi

ok "获取访问令牌成功"

# ------------------------------------------------------------
# Step 2: 获取项目列表（查找或创建默认项目）
# ------------------------------------------------------------
info "查找默认项目..."

PROJECTS_RESPONSE=$(curl -s -X GET "$LANGFUSE_HOST/api/public/projects" \
    -H "Authorization: Bearer $ACCESS_TOKEN" 2>/dev/null || echo "")

# 尝试从项目列表中找我们的项目
PROJECT_ID=""
if [ -n "$PROJECTS_RESPONSE" ]; then
    PROJECT_ID=$(echo "$PROJECTS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    projects = data.get('data', data) if isinstance(data, dict) else data
    if isinstance(projects, list):
        for p in projects:
            if p.get('name') == '$PROJECT_NAME':
                print(p.get('id', ''))
                break
except Exception:
    print('')
" 2>/dev/null || echo "")
fi

if [ -z "$PROJECT_ID" ]; then
    info "创建默认项目: $PROJECT_NAME"
    CREATE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$LANGFUSE_HOST/api/public/projects" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"$PROJECT_NAME\"}" 2>/dev/null || echo "")

    CREATE_CODE=$(echo "$CREATE_RESPONSE" | tail -1)
    CREATE_BODY=$(echo "$CREATE_RESPONSE" | sed '$d')

    if [ "$CREATE_CODE" = "200" ] || [ "$CREATE_CODE" = "201" ]; then
        PROJECT_ID=$(echo "$CREATE_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id', d.get('project',{}).get('id','')) if isinstance(d,dict) else '')" 2>/dev/null || echo "")
        ok "项目创建成功: $PROJECT_NAME"
    else
        warn "创建项目失败 (HTTP $CREATE_CODE): $CREATE_BODY"
        warn "跳过，请手动创建 API Key"
        exit 0
    fi
else
    ok "项目已存在: $PROJECT_NAME ($PROJECT_ID)"
fi

if [ -z "$PROJECT_ID" ]; then
    warn "无法获取项目 ID，请手动创建 API Key"
    exit 0
fi

# ------------------------------------------------------------
# Step 3: 创建 API Key
# ------------------------------------------------------------
info "创建 API Key..."

# Langfuse 创建 API key 的端点
APIKEY_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$LANGFUSE_HOST/api/public/projects/$PROJECT_ID/api-keys" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"note":"nl2sql-auto-generated"}' 2>/dev/null || echo "")

APIKEY_CODE=$(echo "$APIKEY_RESPONSE" | tail -1)
APIKEY_BODY=$(echo "$APIKEY_RESPONSE" | sed '$d')

if [ "$APIKEY_CODE" != "200" ] && [ "$APIKEY_CODE" != "201" ]; then
    # 尝试另一种端点路径
    APIKEY_RESPONSE2=$(curl -s -w "\n%{http_code}" -X POST "$LANGFUSE_HOST/api/project/$PROJECT_ID/api-keys" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"note":"nl2sql-auto-generated"}' 2>/dev/null || echo "")
    APIKEY_CODE=$(echo "$APIKEY_RESPONSE2" | tail -1)
    APIKEY_BODY=$(echo "$APIKEY_RESPONSE2" | sed '$d')
fi

if [ "$APIKEY_CODE" = "200" ] || [ "$APIKEY_CODE" = "201" ]; then
    PUBLIC_KEY=$(echo "$APIKEY_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('publicKey', d.get('public_key','')) if isinstance(d,dict) else '')" 2>/dev/null || echo "")
    SECRET_KEY=$(echo "$APIKEY_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('secretKey', d.get('secret_key','')) if isinstance(d,dict) else '')" 2>/dev/null || echo "")

    # 有些版本返回的字段名不同
    if [ -z "$PUBLIC_KEY" ]; then
        PUBLIC_KEY=$(echo "$APIKEY_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); k=d.get('data',d) if isinstance(d,dict) else d; print(k.get('publicKey',k.get('public_key','')) if isinstance(k,dict) else '')" 2>/dev/null || echo "")
    fi
    if [ -z "$SECRET_KEY" ]; then
        SECRET_KEY=$(echo "$APIKEY_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); k=d.get('data',d) if isinstance(d,dict) else d; print(k.get('secretKey',k.get('secret_key','')) if isinstance(k,dict) else '')" 2>/dev/null || echo "")
    fi
fi

if [ -z "$PUBLIC_KEY" ] || [ -z "$SECRET_KEY" ]; then
    warn "自动创建 API Key 失败（Langfuse API 可能不兼容）"
    warn "请手动在 Langfuse UI 创建: http://localhost:3030"
    warn "  1. 登录（$ADMIN_EMAIL / $ADMIN_PASSWORD）"
    warn "  2. 进入项目 Settings → API Keys → Create API Key"
    warn "  3. 将 Public Key 和 Secret Key 填入 .env"
    exit 0
fi

ok "API Key 创建成功"

# ------------------------------------------------------------
# Step 4: 写入 .env
# ------------------------------------------------------------
info "写入 .env ..."

if [ ! -f .env ]; then
    warn ".env 文件不存在，跳过写入"
    echo ""
    echo "  Public Key: $PUBLIC_KEY"
    echo "  Secret Key: $SECRET_KEY"
    echo ""
    exit 0
fi

# 替换 .env 中的 LANGFUSE_PUBLIC_KEY 和 LANGFUSE_SECRET_KEY
if grep -q '^LANGFUSE_PUBLIC_KEY=' .env; then
    sed -i.bak "s|^LANGFUSE_PUBLIC_KEY=.*|LANGFUSE_PUBLIC_KEY=$PUBLIC_KEY|" .env
else
    echo "LANGFUSE_PUBLIC_KEY=$PUBLIC_KEY" >> .env
fi

if grep -q '^LANGFUSE_SECRET_KEY=' .env; then
    sed -i.bak "s|^LANGFUSE_SECRET_KEY=.*|LANGFUSE_SECRET_KEY=$SECRET_KEY|" .env
else
    echo "LANGFUSE_SECRET_KEY=$SECRET_KEY" >> .env
fi

# 清理 sed 备份
rm -f .env.bak

ok "API Key 已写入 .env"
echo ""
echo -e "${GREEN}  Langfuse 初始化完成！${NC}"
echo ""
echo "  管理员账号: $ADMIN_EMAIL / $ADMIN_PASSWORD"
echo "  项目名称: $PROJECT_NAME"
echo "  UI 地址: $LANGFUSE_HOST"
echo ""
echo "  ⚠️  生产环境请及时修改默认密码！"
echo ""
