# -*- coding: utf-8 -*-
"""
Fix Docker installation on Alibaba Cloud Linux 3
"""
import time
import paramiko

SERVER_IP = "121.41.224.93"
SERVER_USER = "root"
SERVER_PASSWORD = "Fy@20050129"
PROJECT_DIR = "/opt/edu-agent"


def run_cmd(ssh, cmd, timeout=60):
    """Run command and return (stdout, stderr, exit_code)"""
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
    print("[OK] SSH connected\n")

    # ── Step 1: Check OS ──────────────────────────────
    print("=" * 60)
    print("Step 1: Check system info")
    print("=" * 60)
    out, err, _ = run_cmd(ssh, "cat /etc/os-release 2>/dev/null | head -5; uname -m; free -h | head -3")
    print(out)

    # ── Step 2: Install Docker via yum ────────────────
    print("=" * 60)
    print("Step 2: Install Docker via yum (Alibaba Cloud mirror)")
    print("=" * 60)
    out, err, ec = run_cmd(ssh, "yum install -y docker 2>&1", timeout=120)
    print(out[-1000:] if len(out) > 1000 else out)
    if err:
        print("STDERR:", err[-500:] if len(err) > 500 else err)

    if ec != 0:
        # Try dnf
        print("\n[Trying dnf instead...]")
        out, err, ec = run_cmd(ssh, "dnf install -y docker 2>&1", timeout=120)
        print(out[-1000:] if len(out) > 1000 else out)

    # ── Step 3: Start Docker ──────────────────────────
    print("\n" + "=" * 60)
    print("Step 3: Start Docker service")
    print("=" * 60)
    out, err, _ = run_cmd(ssh, "systemctl enable docker && systemctl start docker && docker --version 2>&1")
    print(out)

    # ── Step 4: Install docker-compose binary ─────────
    print("=" * 60)
    print("Step 4: Install docker-compose binary")
    print("=" * 60)
    # Try daocloud mirror first (China accessible)
    install_cmd = """
    # Try to download docker-compose binary
    COMPOSE_VERSION="v2.24.0"
    # Try multiple mirrors
    for url in \\
        "https://ghproxy.com/https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \\
        "https://mirror.ghproxy.com/https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \\
        "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64"
    do
        echo "Trying: $url"
        curl -fSL -o /usr/local/lib/docker/cli-plugins/docker-compose "$url" 2>&1 && break
    done
    # If download failed, try pip install
    if [ ! -f /usr/local/lib/docker/cli-plugins/docker-compose ]; then
        echo "Binary download failed, trying pip..."
        pip3 install docker-compose 2>/dev/null || pip install docker-compose 2>/dev/null || true
    fi
    # Make binary dir and set permissions
    if [ -f /usr/local/lib/docker/cli-plugins/docker-compose ]; then
        chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
        echo "docker-compose binary installed"
        /usr/local/lib/docker/cli-plugins/docker-compose version
    elif command -v docker-compose &>/dev/null; then
        echo "docker-compose (v1) available via pip"
        docker-compose --version
    else
        echo "WARNING: docker-compose not available"
    fi
    """
    out, err, ec = run_cmd(ssh, install_cmd, timeout=120)
    print(out)
    if err:
        print("STDERR:", err[-500:] if len(err) > 500 else err)

    # Also create symlink for backward compat
    run_cmd(ssh, """
    if [ -f /usr/local/lib/docker/cli-plugins/docker-compose ] && [ ! -f /usr/local/bin/docker-compose ]; then
        ln -sf /usr/local/lib/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose 2>/dev/null || true
    fi
    """)

    # ── Step 5: Verify Docker ─────────────────────────
    print("\n" + "=" * 60)
    print("Step 5: Verification")
    print("=" * 60)
    out, err, _ = run_cmd(ssh, "docker --version 2>&1; docker compose version 2>&1 || docker-compose --version 2>&1 || echo 'compose not found'")
    print(out)

    # ── Step 6: Fix docker-compose.yml for old compose ─
    print("=" * 60)
    print("Step 6: Check compose compatibility")
    print("=" * 60)

    # Check if we need to use docker-compose (v1) instead of docker compose (v2)
    out, err, _ = run_cmd(ssh, """
    if docker compose version 2>/dev/null; then
        echo "COMPOSE_V2"
    elif docker-compose --version 2>/dev/null; then
        echo "COMPOSE_V1"
    else
        echo "COMPOSE_NONE"
    fi
    """)
    print(f"Compose type: {out.strip()}")

    # ── Step 7: Start services ────────────────────────
    print("\n" + "=" * 60)
    print("Step 7: Starting EduAgent services...")
    print("=" * 60)

    # Determine compose command
    compose_cmd = "docker compose" if "COMPOSE_V2" in out else "docker-compose"

    out, err, ec = run_cmd(ssh, f"""
    cd {PROJECT_DIR} && {compose_cmd} up -d --build 2>&1
    """, timeout=900)
    print(out[-3000:] if len(out) > 3000 else out)
    if err:
        print("STDERR:", err[-2000:] if len(err) > 2000 else err)

    if ec != 0:
        # If compose fails, try to pull and start services individually
        print("\n[WARN] docker compose failed, checking each service individually...")
        out, err, _ = run_cmd(ssh, f"""
        cd {PROJECT_DIR}
        # Try pulling images first (use mirror)
        docker pull neo4j:5.20-community 2>&1 | tail -5
        docker pull elasticsearch:8.17.4 2>&1 | tail -5
        """, timeout=300)
        print(out)

    # ── Step 8: Show status ───────────────────────────
    print("\n" + "=" * 60)
    print("Step 8: Container status")
    print("=" * 60)
    out, err, _ = run_cmd(ssh, f"cd {PROJECT_DIR} && {compose_cmd} ps 2>&1 || docker ps -a 2>&1")
    print(out)

    # ── Final hints ───────────────────────────────────
    print("\n" + "=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print(f"""
  1. Edit .env with your API keys:
     ssh {SERVER_USER}@{SERVER_IP} 'vim {PROJECT_DIR}/.env'

  2. If services are running, set up Nginx:
     sudo cp {PROJECT_DIR}/nginx/edu-agent.conf /etc/nginx/conf.d/edu-agent.conf
     sudo nginx -t && sudo nginx -s reload

  3. Or open firewall for direct access:
     firewall-cmd --add-port=8800/tcp --permanent && firewall-cmd --reload

  4. Check logs:
     ssh {SERVER_USER}@{SERVER_IP} 'cd {PROJECT_DIR} && {compose_cmd} logs -f app'
""")

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
finally:
    ssh.close()
