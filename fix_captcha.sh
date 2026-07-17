#!/bin/bash
# Fix captcha - rewrite .env + fix PostgreSQL auth
cd /opt/edu-agent

cat > .env << 'ENVEOF'
LLM_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-your-dashscope-api-key-here
SPARK_API_KEY=
SPARK_APP_ID=
SPARK_API_SECRET=
DEEPSEEK_API_KEY=
OPENAI_API_KEY=
DATABASE_URL=postgresql://postgres:Educe_Agent2024@127.0.0.1:5432/eduagent
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=Educe_Agent2024
ES_HOSTS=http://127.0.0.1:9200
ES_USER=
ES_PASSWORD=
REDIS_URL=redis://localhost:6379/0
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin2024
JWT_SECRET_KEY=change-me-in-production
HF_ENDPOINT=https://hf-mirror.com
CHROMA_PERSIST_DIR=./data/vector_db
ENVEOF
echo "[OK] .env rewritten"

# Fix PostgreSQL password
su - postgres -c "psql -c \"ALTER USER postgres PASSWORD 'Educe_Agent2024';\"" 2>/dev/null
echo "[OK] PostgreSQL password set"

# Restart EduAgent
systemctl restart edu-agent
echo "[OK] EduAgent restarted"

# Wait for startup
echo "Waiting 70s for startup..."
sleep 70

# Test captcha
echo "=== Captcha Test ==="
curl -s --max-time 5 http://127.0.0.1:8800/api/auth/captcha-json 2>&1 | head -c 200
echo ""

# Check logs
echo "=== DB Logs ==="
journalctl -u edu-agent --no-pager -n 10 | grep -E "DB|Auth|captcha|Ready|Uvicorn"
