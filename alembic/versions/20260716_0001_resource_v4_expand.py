"""resource v4 expand migration

Revision ID: 20260716_0001
Revises:
Create Date: 2026-07-16
"""
from alembic import op

from src.database.resource_generation_repo import RESOURCE_GENERATION_TABLES_SQL


revision = "20260716_0001"
down_revision = None
branch_labels = ("expand",)
depends_on = None


def upgrade() -> None:
    op.execute(RESOURCE_GENERATION_TABLES_SQL)


def downgrade() -> None:
    # Production rollback keeps the expanded schema so v3 and v4 binaries can
    # coexist for two release cycles. Contract cleanup is a later migration.
    pass
