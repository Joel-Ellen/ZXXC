#!/bin/bash
# Install all Python deps for EduAgent
MIRROR="https://mirrors.aliyun.com/pypi/simple/"
PIP="/usr/local/python310/bin/pip3.10"

$PIP install --upgrade pip -i $MIRROR 2>&1 | tail -3

# Core deps
$PIP install -i $MIRROR loguru openai httpx 2>&1 | tail -5

# Also install everything from requirements.txt (skip already installed)
$PIP install -r /opt/edu-agent/requirements.txt -i $MIRROR 2>&1 | tail -10

echo "=== DEPS INSTALL COMPLETE ==="
echo ""
echo "Now restart: systemctl restart edu-agent"
echo "Check status: systemctl status edu-agent"
echo "Check logs: journalctl -u edu-agent -n 20"
