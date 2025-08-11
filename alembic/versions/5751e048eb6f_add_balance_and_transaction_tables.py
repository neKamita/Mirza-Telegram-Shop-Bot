"""Add balance and transaction tables

Revision ID: 5751e048eb6f_add_balance_and_transaction_tables
Revises: f0809b2c3fbc
Create Date: 2025-01-11 09:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import table, column, text

# revision identifiers, used by Alembic.
revision = '5751e048eb6f_add_balance_and_transaction_tables'
down_revision = 'f0809b2c3fbc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создаем таблицу balances
    op.create_table(
        'balances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.0'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='TON'),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_balances_id'), 'balances', ['id'], unique=False)
    op.create_index(op.f('ix_balances_user_id'), 'balances', ['user_id'], unique=True)

    # Создаем таблицу transactions
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('transaction_type', sa.Enum('purchase', 'refund', 'bonus', 'adjustment', 'recharge', name='transactiontype'), nullable=False),
        sa.Column('status', sa.Enum('pending', 'completed', 'failed', 'cancelled', name='transactionstatus'), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='TON'),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('external_id', sa.String(length=100), nullable=True),
        sa.Column('transaction_metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_id')
    )
    op.create_index(op.f('ix_transactions_id'), 'transactions', ['id'], unique=False)
    op.create_index(op.f('ix_transactions_external_id'), 'transactions', ['external_id'], unique=True)
    op.create_index(op.f('ix_transactions_status'), 'transactions', ['status'], unique=False)
    op.create_index(op.f('ix_transactions_transaction_type'), 'transactions', ['transaction_type'], unique=False)
    op.create_index(op.f('ix_transactions_user_id'), 'transactions', ['user_id'], unique=False)


def downgrade() -> None:
    # Удаляем индексы
    op.drop_index(op.f('ix_transactions_user_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_transaction_type'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_status'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_external_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_id'), table_name='transactions')

    op.drop_index(op.f('ix_balances_user_id'), table_name='balances')
    op.drop_index(op.f('ix_balances_id'), table_name='balances')

    # Удаляем таблицы
    op.drop_table('transactions')
    op.drop_table('balances')

    # Удаляем enum типы
    op.execute('DROP TYPE IF EXISTS transactiontype CASCADE')
    op.execute('DROP TYPE IF EXISTS transactionstatus CASCADE')
