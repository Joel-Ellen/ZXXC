#!/bin/bash
# ============================================================================
# EduAgent Linux 服务器部署脚本
# ============================================================================
# 用法:
#   chmod +x deploy.sh
#   ./deploy.sh              # 首次部署 / 更新部署
#   ./deploy.sh --down       # 停止所有服务
#   ./deploy.sh --logs       # 查看应用日志
#   ./deploy.sh --status     # 查看服务状态
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ──────────────────────────────────────────────────────────────────────────
# 检查依赖
# ──────────────────────────────────────────────────────────────────────────
check_deps() {
    log_info "检查运行环境..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        log_info "Ubuntu/Debian: curl -fsSL https://get.docker.com | bash"
        log_info "CentOS/RHEL:  yum install -y docker-ce"
        exit 1
    fi

    if ! docker compose version &> /dev/null 2>&1; then
        log_error "docker compose 插件未安装，请安装 docker-compose-plugin"
        log_info "sudo apt install docker-compose-plugin   # Ubuntu/Debian"
        exit 1
    fi

    log_ok "Docker 环境就绪"
}

# ──────────────────────────────────────────────────────────────────────────
# 检查 .env 文件
# ──────────────────────────────────────────────────────────────────────────
check_env() {
    if [ ! -f ".env" ]; then
        log_warn ".env 文件不存在，从 .env.example 创建..."
        cp .env.example .env
        log_warn "请编辑 .env 文件填写你的 API Key，然后重新运行此脚本"
        log_info "vim .env"
        exit 1
    fi

    # 检查关键 API Key
    source .env 2>/dev/null || true
    if [ -z "${DASHSCOPE_API_KEY}" ] || [ "${DASHSCOPE_API_KEY}" = "sk-your-dashscope-api-key-here" ]; then
        log_warn "DASHSCOPE_API_KEY 未配置，LLM 将不可用"
    fi
    log_ok ".env 配置已加载"
}

# ──────────────────────────────────────────────────────────────────────────
# 配置 Nginx (提示)
# ──────────────────────────────────────────────────────────────────────────
setup_nginx_hint() {
    echo ""
    log_info "=========================================="
    log_info "  Nginx 配置提示"
    log_info "=========================================="
    echo ""
    echo "  配置文件已位于: nginx/edu-agent.conf"
    echo ""
    echo "  方案 A — 独立域名 (推荐):"
    echo "    1. 编辑 nginx/edu-agent.conf，取消方案 A 的注释"
    echo "    2. 将 server_name 改为你的域名"
    echo "    3. sudo cp nginx/edu-agent.conf /etc/nginx/sites-available/edu-agent"
    echo "    4. sudo ln -s /etc/nginx/sites-available/edu-agent /etc/nginx/sites-enabled/"
    echo "    5. sudo nginx -t && sudo nginx -s reload"
    echo ""
    echo "  方案 B — 路径前缀 (不影响现有项目):"
    echo "    1. 复制方案 B 的 location 块到现有 Nginx server {} 块中"
    echo "    2. 前端需重新构建: vite.config.js 加 base: '/edu/'"
    echo "    3. sudo nginx -t && sudo nginx -s reload"
    echo ""
    log_info "=========================================="
    echo ""
}

# ──────────────────────────────────────────────────────────────────────────
# 部署 (启动/更新)
# ──────────────────────────────────────────────────────────────────────────
deploy() {
    log_info "开始部署 EduAgent..."

    # 拉取基础镜像
    log_info "拉取基础镜像..."
    docker compose pull --ignore-buildable 2>/dev/null || true

    # 构建并启动
    log_info "构建并启动服务..."
    docker compose up -d --build

    # 等待服务就绪
    log_info "等待服务就绪 (可能需要几分钟)..."
    sleep 5

    # 检查状态
    show_status

    echo ""
    log_ok "部署完成！"
    echo ""
    if command -v curl &> /dev/null; then
        log_info "测试 API: curl http://127.0.0.1:8800/api/state"
    fi
}

# ──────────────────────────────────────────────────────────────────────────
# 查看状态
# ──────────────────────────────────────────────────────────────────────────
show_status() {
    echo ""
    log_info "服务状态:"
    echo "============================================"
    docker compose ps
    echo "============================================"
}

# ──────────────────────────────────────────────────────────────────────────
# 停止服务
# ──────────────────────────────────────────────────────────────────────────
down() {
    log_info "停止所有 EduAgent 服务..."
    docker compose down
    log_ok "所有服务已停止"
}

# ──────────────────────────────────────────────────────────────────────────
# 查看日志
# ──────────────────────────────────────────────────────────────────────────
show_logs() {
    docker compose logs -f --tail=100 app
}

# ──────────────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────────────
case "${1:-}" in
    --down)
        down
        ;;
    --logs)
        show_logs
        ;;
    --status)
        show_status
        ;;
    --help|-h)
        echo "用法: ./deploy.sh [选项]"
        echo ""
        echo "  无参数      首次部署 / 更新部署"
        echo "  --down      停止所有服务"
        echo "  --logs      查看后端日志 (Ctrl+C 退出)"
        echo "  --status    查看服务运行状态"
        echo "  --help      显示此帮助"
        ;;
    *)
        check_deps
        check_env
        deploy
        setup_nginx_hint
        ;;
esac
