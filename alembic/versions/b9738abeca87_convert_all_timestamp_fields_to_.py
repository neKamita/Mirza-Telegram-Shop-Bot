"""Convert all timestamp fields to timezone aware

Revision ID: b9738abeca87
Revises: 5751e048eb6f_add_balance_and_transaction_tables
Create Date: 2025-09-13 18:14:22.555912

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9738abeca87'
down_revision: Union[str, Sequence[str], None] = '5751e048eb6f_add_balance_and_transaction_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert all TIMESTAMP fields to TIMESTAMP WITH TIME ZONE."""
    # Обновляем поля в таблице balances
    op.execute("ALTER TABLE balances ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE balances ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE USING updated_at AT TIME ZONE 'UTC'")
    
    # Обновляем поля в таблице transactions
    op.execute("ALTER TABLE transactions ALTER COLUMN created_at TYPE TIMESTAMP WITH TIME ZONE USING created_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE transactions ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE USING updated_at AT TIME ZONE 'UTC'")


def downgrade() -> None:
    """Revert TIMESTAMP WITH TIME ZONE fields back to TIMESTAMP."""
    # Возвращаем поля в таблице transactions к обычному TIMESTAMP
    op.execute("ALTER TABLE transactions ALTER COLUMN updated_at TYPE TIMESTAMP USING updated_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE transactions ALTER COLUMN created_at TYPE TIMESTAMP USING created_at AT TIME ZONE 'UTC'")
    
    # Возвращаем поля в таблице balances к обычному TIMESTAMP
    op.execute("ALTER TABLE balances ALTER COLUMN updated_at TYPE TIMESTAMP USING updated_at AT TIME ZONE 'UTC'")
    op.execute("ALTER TABLE balances ALTER COLUMN created_at TYPE TIMESTAMP USING created_at AT TIME ZONE 'UTC'")
