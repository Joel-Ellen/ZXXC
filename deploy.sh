#!/bin/bash
# ============================================================================
# EduAgent Linux 服务器部署脚本
# ============================================================================
# 用法:
#   chmod +x deploy.sh
#   ./deploy.sh              # 从 EDUAGENT_IMAGE 的不可变 digest 部署
#   ./deploy.sh --down       # 停止所有服务
#   ./deploy.sh --logs       # 查看应用日志
#   ./deploy.sh --status     # 查看服务状态
# ============================================================================

set -euo pipefail

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
        log_error "Docker 未安装，请先按官方文档安装 Docker Engine"
        exit 1
    fi

    if ! docker compose version &> /dev/null 2>&1; then
        log_error "docker compose 插件未安装，请安装 docker-compose-plugin"
        log_info "sudo apt install docker-compose-plugin   # Ubuntu/Debian"
        exit 1
    fi

    if ! command -v cosign &> /dev/null; then
        log_error "Cosign 未安装，无法验证发布镜像签名"
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

    if ! docker compose config --quiet; then
        log_error ".env 缺少生产必填配置或 Compose 配置无效"
        exit 1
    fi
    log_ok ".env 与 Compose 配置校验通过"
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
    echo "  1. 将 nginx/edu-agent.conf 的 server_name 改为正式域名并配置 TLS"
    echo "  2. 安装配置后运行 sudo nginx -t"
    echo "  3. 校验通过后再执行 sudo nginx -s reload"
    echo ""
    log_info "=========================================="
    echo ""
}

# ──────────────────────────────────────────────────────────────────────────
# 部署 (启动/更新)
# ──────────────────────────────────────────────────────────────────────────
deploy() {
    log_info "开始部署 EduAgent..."

    resolved_image="$(docker compose config | awk '
        /^  app:$/ { in_app = 1; next }
        in_app && /^    image:/ { print $2; exit }
        in_app && /^  [^ ]/ { exit }
    ')"
    if [[ ! "$resolved_image" =~ ^[^[:space:]@]+@sha256:[0-9a-f]{64}$ ]]; then
        log_error "EDUAGENT_IMAGE 必须是 CI 发布的不可变 sha256 digest，当前值无效"
        exit 1
    fi

    cosign_identity="${EDUAGENT_COSIGN_IDENTITY:-$(sed -n 's/^EDUAGENT_COSIGN_IDENTITY=//p' .env | tail -n 1 | tr -d '\r')}"
    cosign_issuer="${EDUAGENT_COSIGN_OIDC_ISSUER:-$(sed -n 's/^EDUAGENT_COSIGN_OIDC_ISSUER=//p' .env | tail -n 1 | tr -d '\r')}"
    if [ -z "$cosign_identity" ] || [ -z "$cosign_issuer" ]; then
        log_error "必须配置精确的 EDUAGENT_COSIGN_IDENTITY 和 EDUAGENT_COSIGN_OIDC_ISSUER"
        exit 1
    fi

    log_info "验证镜像的 GitHub OIDC keyless 签名..."
    cosign verify \
        --certificate-identity "$cosign_identity" \
        --certificate-oidc-issuer "$cosign_issuer" \
        "$resolved_image" >/dev/null

    log_info "拉取已验证的不可变镜像: ${resolved_image%@*}@sha256:..."
    docker pull "$resolved_image"
    docker compose pull

    log_info "使用不可变镜像启动服务，禁止在目标主机构建..."
    docker compose up -d --no-build

    # 等待依赖感知的 readiness，失败时禁止宣告部署完成。
    log_info "等待服务就绪 (最多 5 分钟)..."
    if ! command -v curl &> /dev/null; then
        log_error "curl 未安装，无法执行 readiness 检查"
        exit 1
    fi
    ready=0
    for _attempt in $(seq 1 60); do
        if curl -fsS http://127.0.0.1:8800/api/ready >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 5
    done
    if [ "$ready" -ne 1 ]; then
        log_error "服务在 5 分钟内未就绪"
        docker compose logs --tail=100 app
        exit 1
    fi

    # 检查状态
    show_status

    echo ""
    log_ok "部署完成！"
    echo ""
    if command -v curl &> /dev/null; then
        log_info "就绪检查: curl http://127.0.0.1:8800/api/ready"
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
