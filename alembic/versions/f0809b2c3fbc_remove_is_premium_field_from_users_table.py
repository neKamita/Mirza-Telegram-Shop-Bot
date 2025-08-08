"""Remove is_premium field from users table

Revision ID: f0809b2c3fbc
Revises: dfbd1f676ffe
Create Date: 2025-08-08 13:27:39.131996

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0809b2c3fbc'
down_revision: Union[str, Sequence[str], None] = 'dfbd1f676ffe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('users', 'is_premium')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('is_premium', sa.Boolean(), nullable=False, server_default='false'))
