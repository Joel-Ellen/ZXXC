# -*- coding: utf-8 -*-
"""
EduAgent auto deploy script
SCP + SSH deploy to Linux server
"""
import os
import sys
import tarfile
import io
import time
import paramiko
from scp import SCPClient
from pathlib import Path

# ============================================================
# Config
# ============================================================
SERVER_IP = "121.41.224.93"
SERVER_USER = "root"
SERVER_PASSWORD = "Fy@20050129"
SERVER_PORT = 22
PROJECT_DIR = "/opt/edu-agent"
PROJECT_LOCAL = Path(r"c:\Users\17873\Desktop\EduAgent")

# Exclude patterns for tarball
EXCLUDE_PATTERNS = {
    "venv", ".venv", "node_modules", ".git", "__pycache__",
    ".pytest_cache", "edu-agent.tar.gz", "auto_deploy.py",
    ".vscode", ".idea", "logs", "data",
    "frontend/dist", "backups",
}


def create_tarball():
    """Create project tarball in memory"""
    print("[1/5] Packaging project files...")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for item in PROJECT_LOCAL.rglob("*"):
            parts = item.relative_to(PROJECT_LOCAL).parts
            if not parts:
                continue
            # Skip hidden files/dirs
            if any(p.startswith(".") for p in parts):
                continue
            # Skip excluded dirs
            if any(p in EXCLUDE_PATTERNS for p in parts):
                continue
            # Skip pyc
            if item.suffix in {".pyc", ".pyo"}:
                continue
            if item.is_file():
                arcname = str(item.relative_to(PROJECT_LOCAL)).replace("\\", "/")
                tar.add(str(item), arcname=arcname)
    buf.seek(0)
    size_mb = len(buf.getvalue()) / (1024 * 1024)
    print(f"  [OK] Package done: {size_mb:.1f} MB")
    return buf


def deploy():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # ── Connect ────────────────────────────────────
        print(f"\n[2/5] Connecting to {SERVER_USER}@{SERVER_IP}...")
        ssh.connect(
            SERVER_IP, port=SERVER_PORT,
            username=SERVER_USER, password=SERVER_PASSWORD,
            timeout=30,
        )
        print("  [OK] SSH connected")

        # ── Check Docker ───────────────────────────────
        print("\n[3/5] Checking Docker...")
        stdin, stdout, stderr = ssh.exec_command(
            "docker --version 2>/dev/null && echo 'DOCKER_OK' || echo 'DOCKER_MISSING'",
            timeout=10
        )
        docker_check = stdout.read().decode().strip()
        if "DOCKER_MISSING" in docker_check:
            print("  [WARN] Docker not installed, installing...")
            stdin, stdout, stderr = ssh.exec_command(
                "curl -fsSL https://get.docker.com | bash 2>&1",
                timeout=180
            )
            out = stdout.read().decode()
            err = stderr.read().decode()
            print(out[-500:] if len(out) > 500 else out)
            if err:
                print("STDERR:", err[-500:] if len(err) > 500 else err)

            time.sleep(3)
            ssh.exec_command("systemctl enable docker && systemctl start docker", timeout=30)
            print("  [OK] Docker installed")

            # Install docker compose plugin
            print("  Installing docker compose plugin...")
            stdin, stdout, stderr = ssh.exec_command(
                "apt-get update -qq && apt-get install -y -qq docker-compose-plugin 2>/dev/null || "
                "yum install -y docker-compose-plugin 2>/dev/null || true",
                timeout=60
            )
            out = stdout.read().decode()
            err = stderr.read().decode()
            if out:
                print(out[-300:])
        else:
            ver = docker_check.split('\n')[0] if docker_check else docker_check
            print(f"  [OK] {ver}")

        # Check docker compose
        stdin, stdout, stderr = ssh.exec_command(
            "docker compose version 2>/dev/null && echo 'COMPOSE_OK' || echo 'COMPOSE_MISSING'",
            timeout=10
        )
        compose_check = stdout.read().decode().strip()
        if "COMPOSE_OK" in compose_check:
            print("  [OK] docker compose available")
        else:
            print("  [WARN] docker compose not available, trying to install...")
            stdin, stdout, stderr = ssh.exec_command(
                "apt-get install -y -qq docker-compose-plugin 2>/dev/null || "
                "yum install -y docker-compose-plugin 2>/dev/null || "
                "echo 'MANUAL_INSTALL_REQUIRED'",
                timeout=60
            )
            result = stdout.read().decode().strip()
            if "MANUAL_INSTALL_REQUIRED" in result:
                print("  [ERROR] Please install docker compose plugin manually")
                print("  See: https://docs.docker.com/compose/install/linux/")

        # ── Upload files ───────────────────────────────
        print(f"\n[4/5] Uploading project to {PROJECT_DIR}...")
        tarball = create_tarball()

        ssh.exec_command(f"mkdir -p {PROJECT_DIR}", timeout=10)

        with SCPClient(ssh.get_transport(), socket_timeout=120) as scp:
            scp.putfo(tarball, f"{PROJECT_DIR}/edu-agent.tar.gz")

        print("  [OK] Upload done, extracting...")
        stdin, stdout, stderr = ssh.exec_command(
            f"cd {PROJECT_DIR} && tar xzf edu-agent.tar.gz && rm -f edu-agent.tar.gz && echo 'EXTRACT_OK'",
            timeout=30
        )
        result = stdout.read().decode().strip()
        err_result = stderr.read().decode().strip()
        if "EXTRACT_OK" in result:
            print("  [OK] Extract done")
        else:
            print(f"  [WARN] Extract may have failed: {err_result[:200] if err_result else 'no output'}")

        # ── Setup .env ─────────────────────────────────
        print("\n[5/5] Setting up environment...")
        stdin, stdout, stderr = ssh.exec_command(
            f"cd {PROJECT_DIR} && "
            "if [ ! -f .env ]; then cp .env.example .env && echo 'ENV_CREATED'; else echo 'ENV_EXISTS'; fi",
            timeout=10
        )
        env_status = stdout.read().decode().strip()
        if "ENV_CREATED" in env_status:
            print("  [WARN] .env created from template, please edit it with your API Key!")
            print(f"  Run: ssh {SERVER_USER}@{SERVER_IP} 'vim {PROJECT_DIR}/.env'")
        else:
            print("  [OK] .env already exists")

        # ── Start Docker Compose ───────────────────────
        print("\n" + "=" * 60)
        print("  Starting Docker Compose (this may take 5-10 minutes)...")
        print("=" * 60)
        stdin, stdout, stderr = ssh.exec_command(
            f"cd {PROJECT_DIR} && docker compose up -d --build 2>&1",
            timeout=900,
        )
        # Stream output
        while not stdout.channel.exit_status_ready:
            if stdout.channel.recv_ready():
                line = stdout.channel.recv(4096).decode('utf-8', errors='replace')
                print(line, end="", flush=True)
            time.sleep(0.3)
        # Drain remaining
        try:
            remaining = stdout.read().decode('utf-8', errors='replace')
            if remaining:
                print(remaining)
        except:
            pass

        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            err_out = stderr.read().decode('utf-8', errors='replace')
            print(f"\n[WARN] docker compose exited with code {exit_code}")
            if err_out:
                print(err_out[-1000:])

        # ── Check status ───────────────────────────────
        print("\n" + "=" * 60)
        print("  Service Status:")
        print("=" * 60)
        stdin, stdout, stderr = ssh.exec_command(
            f"cd {PROJECT_DIR} && docker compose ps 2>&1",
            timeout=30
        )
        print(stdout.read().decode('utf-8', errors='replace'))

        # ── Nginx hint ─────────────────────────────────
        print("\n" + "=" * 60)
        print("  Nginx Config Hint")
        print("=" * 60)
        print(f"""
  Your server already has Nginx. To set up reverse proxy:

  Method A - Independent domain (recommended):
    1. Edit config: vim {PROJECT_DIR}/nginx/edu-agent.conf
       (Uncomment "Method A", change server_name to your domain)
    2. sudo cp {PROJECT_DIR}/nginx/edu-agent.conf /etc/nginx/conf.d/edu-agent.conf
    3. sudo nginx -t && sudo nginx -s reload

  Method B - Quick test (open port 8800):
    firewall-cmd --add-port=8800/tcp --permanent 2>/dev/null && firewall-cmd --reload 2>/dev/null || \\
    iptables -I INPUT -p tcp --dport 8800 -j ACCEPT

  Then visit: http://{SERVER_IP}:8800
""")

        print("[DONE] Deployment complete!")
        print(f"  Verify: curl http://127.0.0.1:8800/api/state")

    except Exception as e:
        print(f"\n[ERROR] Deployment failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        ssh.close()


if __name__ == "__main__":
    deploy()
