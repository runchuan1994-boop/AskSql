#!/usr/bin/env bash
# ============================================================
# NL2SQL Agent - 一键部署脚本
# ============================================================
# 用法:
#   ./run.sh              # 交互式部署（引导配置并启动）
#   ./run.sh start        # 启动服务（已有 .env 时直接用）
#   ./run.sh stop         # 停止服务
#   ./run.sh restart      # 重启服务
#   ./run.sh build        # 重新构建镜像
#   ./run.sh logs         # 查看日志
#   ./run.sh down         # 停止并移除容器
#   ./run.sh clean        # 彻底清理（容器 + 数据 + 镜像）
#   ./run.sh status       # 查看运行状态
#   ./run.sh test         # 运行后端测试
# ============================================================

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 获取脚本所在目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn()    { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗]${NC} $1" >&2; }
step()    { echo -e "\n${CYAN}▶ $1${NC}"; }
banner()  { echo -e "\n${BOLD}${GREEN}$1${NC}\n"; }

# ------------------------------------------------------------
# 前置检查
# ------------------------------------------------------------

check_prerequisites() {
    step "检查运行环境..."

    local missing=0

    # Docker
    if command -v docker &> /dev/null; then
        success "Docker: $(docker --version | awk '{print $3}')"
    else
        error "Docker 未安装，请先安装 Docker: https://docs.docker.com/get-docker/"
        missing=1
    fi

    # Docker Compose
    if docker compose version &> /dev/null; then
        success "Docker Compose: $(docker compose version | awk '{print $4}')"
    elif command -v docker-compose &> /dev/null; then
        success "Docker Compose (standalone): $(docker-compose --version | awk '{print $3}')"
        # 兼容老版本 docker-compose
        export DOCKER_COMPOSE_CMD="docker-compose"
    else
        error "Docker Compose 未安装"
        missing=1
    fi

    if [ $missing -eq 1 ]; then
        error "缺少必要依赖，请先安装后重试。"
        exit 1
    fi

    success "环境检查通过"
}

# ------------------------------------------------------------
# 环境变量配置
# ------------------------------------------------------------

configure_env() {
    if [ -f .env ]; then
        info ".env 文件已存在，跳过配置。"
        return 0
    fi

    step "配置环境变量..."
    echo ""
    echo -e "${BOLD}请选择 LLM 提供商:${NC}"
    echo "  1) Claude (Anthropic) - 默认推荐"
    echo "  2) OpenAI"
    echo "  3) 本地 OpenAI 兼容模型"
    echo ""
    read -p "请输入选项 [1-3，默认 1]: " llm_choice
    llm_choice=${llm_choice:-1}

    case $llm_choice in
        1)
            provider="claude"
            read -p "请输入 ANTHROPIC_API_KEY: " api_key
            if [ -z "$api_key" ]; then
                warn "API Key 为空，后续请在 .env 文件中手动配置。"
            fi
            read -p "请输入模型名称 [默认 claude-sonnet-4-20250514]: " model
            model=${model:-claude-sonnet-4-20250514}
            ;;
        2)
            provider="openai"
            read -p "请输入 OPENAI_API_KEY: " api_key
            if [ -z "$api_key" ]; then
                warn "API Key 为空，后续请在 .env 文件中手动配置。"
            fi
            read -p "请输入模型名称 [默认 gpt-4o]: " model
            model=${model:-gpt-4o}
            ;;
        3)
            provider="local_openai_compatible"
            read -p "请输入 API Key [可留空]: " api_key
            api_key=${api_key:-sk-placeholder}
            read -p "请输入 API Base URL (例如 http://localhost:8080/v1): " base_url
            if [ -z "$base_url" ]; then
                warn "Base URL 为空，后续请在 .env 文件中手动配置。"
            fi
            read -p "请输入模型名称 [默认 gpt-4o]: " model
            model=${model:-gpt-4o}
            ;;
        *)
            error "无效选项"
            exit 1
            ;;
    esac

    # 从模板生成 .env
    cp .env.example .env

    # 写入配置
    sed -i.bak "s/^LLM_PROVIDER=.*/LLM_PROVIDER=$provider/" .env

    if [ "$provider" = "claude" ]; then
        sed -i.bak "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$api_key|" .env
        sed -i.bak "s|^ANTHROPIC_MODEL=.*|ANTHROPIC_MODEL=$model|" .env
    elif [ "$provider" = "openai" ]; then
        sed -i.bak "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$api_key|" .env
        sed -i.bak "s|^OPENAI_MODEL=.*|OPENAI_MODEL=$model|" .env
    elif [ "$provider" = "local_openai_compatible" ]; then
        sed -i.bak "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$api_key|" .env
        sed -i.bak "s|^OPENAI_BASE_URL=.*|OPENAI_BASE_URL=$base_url|" .env
        sed -i.bak "s|^OPENAI_MODEL=.*|OPENAI_MODEL=$model|" .env
    fi

    rm -f .env.bak

    success ".env 配置文件已生成"
    info "如需修改其他参数，请编辑 .env 文件"
}

# ------------------------------------------------------------
# 构建与启动
# ------------------------------------------------------------

build_images() {
    step "构建 Docker 镜像..."

    if [ "${1:-}" = "--no-cache" ]; then
        info "使用 --no-cache 模式重新构建"
        docker compose build --no-cache
    else
        docker compose build
    fi

    success "镜像构建完成"
}

start_services() {
    step "启动服务..."

    # 确保数据目录存在
    mkdir -p backend/data backend/config/schemas backend/config/projects

    docker compose up -d

    # 等待服务启动
    step "等待服务就绪..."

    local max_wait=60
    local waited=0
    local backend_ready=0

    while [ $waited -lt $max_wait ]; do
        if curl -sf http://localhost:8000/health &> /dev/null; then
            backend_ready=1
            break
        fi
        sleep 2
        waited=$((waited + 2))
        echo -n "."
    done
    echo ""

    if [ $backend_ready -eq 1 ]; then
        success "后端服务已就绪（等待了 ${waited}s）"
    else
        warn "后端服务健康检查超时，请手动检查: docker compose logs backend"
    fi

    # 前端静态服务一般很快，简单确认容器在跑
    if docker compose ps frontend --format json 2>/dev/null | grep -q "running"; then
        success "前端服务已启动"
    fi
}

print_access_info() {
    banner "  NL2SQL Agent 部署成功！"

    echo -e "  ${BOLD}前端地址:${NC}  http://localhost:5173"
    echo -e "  ${BOLD}后端 API:${NC}  http://localhost:8000"
    echo -e "  ${BOLD}API 文档:${NC}  http://localhost:8000/docs"
    echo -e "  ${BOLD}健康检查:${NC}  http://localhost:8000/health"
    echo ""
    echo -e "  常用命令:"
    echo -e "    ${CYAN}./run.sh logs${NC}    查看实时日志"
    echo -e "    ${CYAN}./run.sh stop${NC}    停止服务"
    echo -e "    ${CYAN}./run.sh status${NC}  查看状态"
    echo ""
}

# ------------------------------------------------------------
# 其他命令
# ------------------------------------------------------------

stop_services() {
    step "停止服务..."
    docker compose stop
    success "服务已停止"
}

restart_services() {
    step "重启服务..."
    docker compose restart
    success "服务已重启"
}

show_logs() {
    info "查看实时日志（Ctrl+C 退出）..."
    docker compose logs -f --tail=100 "$@"
}

show_status() {
    step "服务状态"
    echo ""
    docker compose ps
    echo ""

    # 健康检查
    if curl -sf http://localhost:8000/health &> /dev/null; then
        local health=$(curl -s http://localhost:8000/health 2>/dev/null || echo "{}")
        success "后端健康: $health"
    else
        warn "后端健康检查失败（服务可能未启动）"
    fi

    if curl -sf http://localhost:5173 &> /dev/null; then
        success "前端可达: http://localhost:5173"
    else
        warn "前端不可达（服务可能未启动）"
    fi
}

teardown() {
    step "停止并移除容器..."
    docker compose down
    success "容器已移除"
}

clean_all() {
    warn "即将彻底清理所有数据和镜像！"
    read -p "确定要继续吗？此操作不可恢复 [y/N]: " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        info "已取消"
        exit 0
    fi

    step "停止并移除所有容器和卷..."
    docker compose down -v --rmi all

    step "清理本地数据..."
    rm -rf backend/data/*.db
    rm -rf backend/__pycache__ backend/nl2sql/__pycache__
    rm -rf frontend/dist

    success "清理完成"
}

run_tests() {
    step "运行后端测试..."
    docker compose run --rm backend pytest tests/ -v
}

# ------------------------------------------------------------
# 主流程
# ------------------------------------------------------------

main() {
    local cmd="${1:-}"

    case $cmd in
        start)
            check_prerequisites
            if [ ! -f .env ]; then
                configure_env
            fi
            build_images
            start_services
            print_access_info
            ;;

        stop)
            check_prerequisites
            stop_services
            ;;

        restart)
            check_prerequisites
            restart_services
            ;;

        build)
            check_prerequisites
            build_images "${2:-}"
            ;;

        logs)
            shift
            show_logs "$@"
            ;;

        down)
            check_prerequisites
            teardown
            ;;

        clean)
            check_prerequisites
            clean_all
            ;;

        status)
            check_prerequisites
            show_status
            ;;

        test)
            check_prerequisites
            run_tests
            ;;

        "")
            # 默认：交互式一键部署
            banner "  NL2SQL Agent - 一键部署"
            check_prerequisites
            configure_env
            build_images
            start_services
            print_access_info
            ;;

        -h|--help|help)
            cat << 'EOF'
NL2SQL Agent - 一键部署脚本

用法:
  ./run.sh              交互式部署（引导配置并启动）
  ./run.sh start        启动服务（已有 .env 时直接启动）
  ./run.sh stop         停止服务
  ./run.sh restart      重启服务
  ./run.sh build        构建 Docker 镜像
  ./run.sh build --no-cache  无缓存重新构建
  ./run.sh logs         查看实时日志
  ./run.sh logs backend  只看后端日志
  ./run.sh logs frontend 只看前端日志
  ./run.sh down         停止并移除容器
  ./run.sh clean        彻底清理（容器 + 数据 + 镜像）
  ./run.sh status       查看运行状态
  ./run.sh test         运行后端测试
  ./run.sh help         显示帮助

示例:
  ./run.sh              # 首次部署，引导配置
  ./run.sh start        # 后续启动
  ./run.sh logs backend # 看后端日志
EOF
            ;;

        *)
            error "未知命令: $cmd"
            echo "使用 ./run.sh help 查看帮助"
            exit 1
            ;;
    esac
}

main "$@"
