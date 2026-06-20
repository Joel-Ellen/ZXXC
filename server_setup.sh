#!/bin/bash
# ============================================================================
# EduAgent 服务器一键部署脚本
# 在服务器上直接运行: bash server_setup.sh
# ============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

PROJECT_DIR="/opt/edu-agent"
PYTHON_BIN=""

# ========================================================================
# Step 1: 检查/安装 Python 3.10+
# ========================================================================
log_info "Step 1: Setting up Python 3.10+..."

# Check if Python 3.10+ already exists
for py in python3.12 python3.11 python3.10; do
    if command -v $py &>/dev/null; then
        ver=$($py --version 2>&1)
        log_ok "Found $ver"
        PYTHON_BIN=$(command -v $py)
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    log_info "Installing Python 3.10 from source (this takes 5-10 minutes)..."

    # Download source
    cd /tmp
    if [ ! -f Python-3.10.11.tar.xz ]; then
        log_info "Downloading Python 3.10.11..."
        curl -fsSL -o Python-3.10.11.tar.xz \
            "https://npmmirror.com/mirrors/python/3.10.11/Python-3.10.11.tar.xz" || \
        curl -fsSL -o Python-3.10.11.tar.xz \
            "https://www.python.org/ftp/python/3.10.11/Python-3.10.11.tar.xz"
    fi

    # Extract
    tar xf Python-3.10.11.tar.xz
    cd Python-3.10.11

    # Build (use -j1 to avoid OOM on low-memory servers)
    log_info "Configuring..."
    ./configure --prefix=/usr/local/python310 --enable-loadable-sqlite-extensions 2>&1 | tail -3

    log_info "Compiling (this will take a while)..."
    make -j1 2>&1 | tail -5
    make install 2>&1 | tail -3

    PYTHON_BIN="/usr/local/python310/bin/python3.10"
    ln -sf $PYTHON_BIN /usr/local/bin/python3.10 2>/dev/null || true

    log_ok "Python 3.10 installed at $PYTHON_BIN"
    $PYTHON_BIN --version
fi

# ========================================================================
# Step 2: 安装 Python 依赖
# ========================================================================
log_info "Step 2: Installing Python dependencies..."

PIP="${PYTHON_BIN} -m pip"
MIRROR="https://mirrors.aliyun.com/pypi/simple/"

$PIP install --upgrade pip -i $MIRROR 2>&1 | tail -3

log_info "Installing core packages..."
$PIP install --no-cache-dir -i $MIRROR \
    starlette uvicorn sse-starlette fastapi \
    pydantic PyJWT argon2-cffi python-dotenv tenacity \
    numpy aiohttp \
    langgraph langchain-core langchain-text-splitters \
    neo4j elasticsearch pymilvus \
    2>&1 | tail -10

log_ok "Python dependencies installed"

# ========================================================================
# Step 3: 检查 .env
# ========================================================================
log_info "Step 3: Checking .env configuration..."

cd $PROJECT_DIR

if [ ! -f .env ]; then
    cp .env.example .env
    log_warn ".env created from template - YOU MUST EDIT IT!"
    log_warn "Run: vim $PROJECT_DIR/.env"
    log_warn "Add your DASHSCOPE_API_KEY (required for LLM)"
else
    # Check if API key is set
    if grep -q "sk-your-dashscope-api-key-here" .env 2>/dev/null; then
        log_warn "DASHSCOPE_API_KEY not set in .env - LLM will not work!"
    else
        log_ok ".env looks configured"
    fi
fi

# ========================================================================
# Step 4: 先手动测试
# ========================================================================
log_info "Step 4: Testing server startup..."

# Kill any existing instance
pkill -f "frontend/server.py" 2>/dev/null || true
sleep 1

# Test run (timeout after 10 seconds)
cd $PROJECT_DIR
timeout 10 $PYTHON_BIN frontend/server.py 2>&1 | head -30 &
TEST_PID=$!
sleep 8

# Check if it's running
if kill -0 $TEST_PID 2>/dev/null; then
    log_ok "Server started successfully!"
    # Test API
    sleep 2
    if curl -s http://127.0.0.1:8800/api/state > /dev/null 2>&1; then
        log_ok "API responding on port 8800"
        curl -s http://127.0.0.1:8800/api/state | head -5
    fi
    kill $TEST_PID 2>/dev/null || true
else
    log_warn "Server may have startup issues, checking..."
    # The server might have died - let's still proceed with systemd
fi

wait $TEST_PID 2>/dev/null || true

# ========================================================================
# Step 5: 创建 systemd 服务
# ========================================================================
log_info "Step 5: Creating systemd service..."

cat > /etc/systemd/system/edu-agent.service << SERVICEEOF
[Unit]
Description=EduAgent Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment=PATH=/usr/local/bin:/usr/local/python310/bin:/usr/bin:/bin
Environment=HF_ENDPOINT=https://hf-mirror.com
ExecStart=$PYTHON_BIN $PROJECT_DIR/frontend/server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload
systemctl enable edu-agent
systemctl restart edu-agent

sleep 3

# Check status
if systemctl is-active --quiet edu-agent; then
    log_ok "EduAgent service is running!"
else
    log_warn "Service failed to start. Checking logs..."
    journalctl -u edu-agent --no-pager -n 20
fi

# ========================================================================
# Step 6: Nginx 配置提示
# ========================================================================
echo ""
echo "============================================"
echo "  DEPLOYMENT COMPLETE"
echo "============================================"
echo ""
echo "  Service:  systemctl status edu-agent"
echo "  Logs:     journalctl -u edu-agent -f"
echo "  API test: curl http://127.0.0.1:8800/api/state"
echo ""
echo "  For external access, open firewall:"
echo "    firewall-cmd --add-port=8800/tcp --permanent && firewall-cmd --reload"
echo "    # Then visit: http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP'):8800"
echo ""
echo "  To integrate with existing Nginx:"
echo "    # Review and copy:"
echo "    cat $PROJECT_DIR/nginx/edu-agent.conf"
echo "    # Edit for your setup, then:"
echo "    cp $PROJECT_DIR/nginx/edu-agent.conf /etc/nginx/conf.d/edu-agent.conf"
echo "    nginx -t && nginx -s reload"
echo ""
echo "  IMPORTANT: Edit .env if you haven't yet:"
echo "    vim $PROJECT_DIR/.env"
echo ""
