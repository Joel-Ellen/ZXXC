# -*- coding: utf-8 -*-
"""
EduAgent lightweight deploy — run directly on server (no Docker)
For servers with limited resources (2GB RAM)
"""
import time
import paramiko

SERVER_IP = "121.41.224.93"
SERVER_USER = "root"
SERVER_PASSWORD = "Fy@20050129"
PROJECT_DIR = "/opt/edu-agent"


def run_cmd(ssh, cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    exit_code = stdout.channel.recv_exit_status()
    return out, err, exit_code


ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print(f"Connecting to {SERVER_USER}@{SERVER_IP}...")
    ssh.connect(SERVER_IP, port=22, username=SERVER_USER, password=SERVER_PASSWORD, timeout=30)
    print("[OK] Connected\n")

    # ================================================================
    # Step 1: Install Node.js for frontend build
    # ================================================================
    print("=" * 60)
    print("Step 1: Installing Node.js 20.x")
    print("=" * 60)
    cmd = """
    if ! command -v node &>/dev/null; then
        # Install Node.js 20.x via NodeSource
        curl -fsSL https://deb.nodesource.com/setup_20.x 2>/dev/null | bash - 2>/dev/null && \\
            apt-get install -y nodejs 2>/dev/null && echo "NODE_OK_APT" || \\
        # Fallback: download binary from npmmirror (China mirror)
        (
            cd /usr/local
            curl -fsSL https://npmmirror.com/mirrors/node/v20.11.0/node-v20.11.0-linux-x64.tar.xz -o node.tar.xz 2>/dev/null && \\
            tar xf node.tar.xz && rm node.tar.xz && \\
            ln -sf /usr/local/node-v20.11.0-linux-x64/bin/node /usr/local/bin/node && \\
            ln -sf /usr/local/node-v20.11.0-linux-x64/bin/npm /usr/local/bin/npm && \\
            ln -sf /usr/local/node-v20.11.0-linux-x64/bin/npx /usr/local/bin/npx && \\
            echo "NODE_OK_BINARY"
        )
    else
        echo "NODE_ALREADY_INSTALLED"
        node --version
    fi
    """
    out, err, ec = run_cmd(ssh, cmd, timeout=180)
    print(out[-800:] if len(out) > 800 else out)
    if err:
        print("STDERR:", err[-400:])

    # Verify node
    out, err, ec = run_cmd(ssh, "node --version 2>&1; npm --version 2>&1")
    print("Node:", out.strip().replace('\n', ', '))

    # ================================================================
    # Step 2: Build frontend
    # ================================================================
    print("\n" + "=" * 60)
    print("Step 2: Building frontend (Vue 3 + Vite)")
    print("=" * 60)
    cmd = f"""
    cd {PROJECT_DIR}/frontend
    # Use npmmirror for faster install
    npm config set registry https://registry.npmmirror.com 2>/dev/null || true
    npm install 2>&1 | tail -5
    npm run build 2>&1
    echo "BUILD_EXIT=$?"
    """
    out, err, ec = run_cmd(ssh, cmd, timeout=300)
    print(out[-2000:] if len(out) > 2000 else out)
    if err:
        print("STDERR:", err[-1000:] if len(err) > 1000 else err)

    # ================================================================
    # Step 3: Install Python dependencies
    # ================================================================
    print("\n" + "=" * 60)
    print("Step 3: Installing Python dependencies (pip3.9)")
    print("=" * 60)
    cmd = f"""
    cd {PROJECT_DIR}
    pip3.9 install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ 2>&1 | tail -20
    echo "PIP_EXIT=$?"
    """
    out, err, ec = run_cmd(ssh, cmd, timeout=300)
    print(out[-2000:] if len(out) > 2000 else out)
    if err and "WARNING" not in err:
        print("STDERR:", err[-1000:] if len(err) > 1000 else err)

    # ================================================================
    # Step 4: Set up .env
    # ================================================================
    print("\n" + "=" * 60)
    print("Step 4: Checking .env config")
    print("=" * 60)
    out, err, ec = run_cmd(ssh, f"cd {PROJECT_DIR} && cat .env 2>/dev/null | grep -v '^#' | grep -v '^$' || echo 'NO_ENV'")
    print(out[:500])

    # ================================================================
    # Step 5: Create systemd service
    # ================================================================
    print("\n" + "=" * 60)
    print("Step 5: Creating systemd service")
    print("=" * 60)
    service_content = f"""[Unit]
Description=EduAgent Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={PROJECT_DIR}
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/local/bin/python3.9 {PROJECT_DIR}/frontend/server.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    cmd = f"""cat > /etc/systemd/system/edu-agent.service << 'SERVICEEOF'
{service_content}
SERVICEEOF
systemctl daemon-reload
echo "Service created"
"""
    out, err, ec = run_cmd(ssh, cmd)
    print(out)

    # ================================================================
    # Step 6: Start service
    # ================================================================
    print("\n" + "=" * 60)
    print("Step 6: Starting EduAgent service")
    print("=" * 60)
    out, err, ec = run_cmd(ssh, "systemctl enable edu-agent && systemctl start edu-agent && sleep 3 && systemctl status edu-agent 2>&1 | head -20", timeout=30)
    print(out)

    # Check if it's running
    out, err, ec = run_cmd(ssh, "curl -s http://127.0.0.1:8800/api/state 2>&1 | head -5")
    print("\nAPI Test:", out[:300] if out else "No response")

    # ================================================================
    # Step 7: Nginx integration
    # ================================================================
    print("\n" + "=" * 60)
    print("Step 7: Nginx setup for existing project coexistence")
    print("=" * 60)

    # Check existing nginx config
    out, err, ec = run_cmd(ssh, "ls /etc/nginx/conf.d/ 2>/dev/null; echo '---'; nginx -t 2>&1 | head -5")
    print("Existing nginx:\n", out)

    # Add EduAgent location to existing nginx under /edu/ path
    # First check what server blocks exist
    out, err, ec = run_cmd(ssh, "grep -r 'server_name\\|listen' /etc/nginx/ 2>/dev/null | grep -v '#.*server_name' | head -10")
    print("Existing server configs:\n", out)

    print("\n" + "=" * 60)
    print("DEPLOYMENT COMPLETE")
    print("=" * 60)
    print(f"""
  Project: {PROJECT_DIR}
  Service: systemctl status edu-agent
  Logs:    journalctl -u edu-agent -f

  Quick test (on server):
    curl http://127.0.0.1:8800/api/state

  For external access, run on server:
    # Option A: Add to existing nginx as /edu/ path:
    echo 'See {PROJECT_DIR}/nginx/edu-agent.conf for config snippets'

    # Option B: Open port directly (quick test):
    firewall-cmd --add-port=8800/tcp --permanent && firewall-cmd --reload
    # Then visit: http://{SERVER_IP}:8800
""")

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
