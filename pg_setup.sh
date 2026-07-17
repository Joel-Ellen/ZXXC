#!/bin/bash
# PostgreSQL setup for EduAgent
PG_USER="postgres"
PG_PASS="Educe_Agent2024"
DB_NAME="eduagent"

# Create database
su - postgres -c "psql -c 'CREATE DATABASE $DB_NAME;'" 2>/dev/null || echo "DB may already exist"

# Set password
su - postgres -c "psql -c \"ALTER USER $PG_USER PASSWORD '$PG_PASS';\""

# Verify
su - postgres -c "psql -c '\l'" | grep $DB_NAME && echo "[OK] Database $DB_NAME ready"

# Configure low memory
PG_CONF="/var/lib/pgsql/data/postgresql.conf"
sed -i 's/^#*shared_buffers.*/shared_buffers = 128MB/' $PG_CONF
sed -i 's/^#*effective_cache_size.*/effective_cache_size = 256MB/' $PG_CONF
sed -i 's/^#*work_mem.*/work_mem = 4MB/' $PG_CONF
sed -i 's/^#*maintenance_work_mem.*/maintenance_work_mem = 32MB/' $PG_CONF
systemctl restart postgresql
systemctl is-active postgresql && echo "[OK] PostgreSQL restarted with low-memory config"
