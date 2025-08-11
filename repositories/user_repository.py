"""
Репозиторий для работы с пользователями через PostgreSQL (Neon)
"""
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, insert, update
from typing import Dict, Any, Optional
from core.interfaces import DatabaseInterface
from sqlalchemy import Column, Integer, Boolean, DateTime, String, Numeric, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum
from services.user_cache import UserCache


class TransactionType(PyEnum):
    """Типы транзакций"""
    PURCHASE = "purchase"  # Покупка звезд
    REFUND = "refund"     # Возврат
    BONUS = "bonus"       # Бонусные начисления
    ADJUSTMENT = "adjustment"  # Корректировка
    RECHARGE = "recharge"  # Пополнение баланса


class TransactionStatus(PyEnum):
    """Статусы транзакций"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи с балансом и транзакциями
    balances = relationship("Balance", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")

    def __init__(self, database_url: str, user_cache: Optional[UserCache] = None):
        self.database_url = database_url
        self.user_cache = user_cache


class Balance(Base):
    """Модель баланса пользователя"""
    __tablename__ = "balances"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    amount = Column(Numeric(10, 2), nullable=False, default=0.0)  # Баланс в виде числа с плавающей точкой
    currency = Column(String(3), nullable=False, default="TON")    # Валюта (TON, USD и т.д.)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связь с пользователем
    user = relationship("User", back_populates="balances")

    def __repr__(self):
        return f"<Balance(user_id={self.user_id}, amount={self.amount}, currency='{self.currency}')>"


class Transaction(Base):
    """Модель транзакций пользователя"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_type = Column(Enum(TransactionType), nullable=False, index=True)
    status = Column(Enum(TransactionStatus), nullable=False, default=TransactionStatus.PENDING, index=True)
    amount = Column(Numeric(10, 2), nullable=False)  # Сумма транзакции
    currency = Column(String(3), nullable=False, default="TON")
    description = Column(String(500), nullable=True)  # Описание транзакции
    external_id = Column(String(100), nullable=True, unique=True, index=True)  # ID внешней системы (Heleket)
    transaction_metadata = Column(String(1000), nullable=True)  # Дополнительные данные в JSON формате
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связь с пользователем
    user = relationship("User", back_populates="transactions")

    def __repr__(self):
        return f"<Transaction(id={self.id}, user_id={self.user_id}, type={self.transaction_type.value}, amount={self.amount})>"

class UserRepository(DatabaseInterface):
    """Репозиторий для управления пользователями через PostgreSQL"""

    def __init__(self, database_url: str, user_cache: Optional[UserCache] = None):
        self.database_url = database_url
        self.user_cache = user_cache
        self.logger = logging.getLogger(__name__)
        self.engine = create_async_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True
        )
        self.async_session = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def create_tables(self) -> None:
        """Создание таблиц в базе данных"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def add_user(self, user_id: int) -> bool:
        """Добавление пользователя в базу данных"""
        async with self.async_session() as session:
            try:
                stmt = insert(User).values(user_id=user_id)
                await session.execute(stmt)
                # Инвалидируем кеш пользователя
                if self.user_cache:
                    await self.user_cache.invalidate_user_cache(user_id)
                await session.commit()
                return True
            except Exception:
                await session.rollback()
                return False

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользователя по ID с использованием Cache-Aside паттерна"""
        # Сначала пытаемся получить из кеша
        if self.user_cache:
            cached_user = await self.user_cache.get_user_profile(user_id)
            if cached_user:
                return cached_user

        # Если в кеше нет, получаем из базы данных
        async with self.async_session() as session:
            stmt = select(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user:
                user_data = {
                    "id": user.id,
                    "user_id": user.user_id,
                    "created_at": user.created_at
                }

                # Кешируем результат
                if self.user_cache:
                    await self.user_cache.cache_user_profile(user_id, user_data)

                return user_data
            return None



    async def user_exists(self, user_id: int) -> bool:
        """Проверка существования пользователя"""
        async with self.async_session() as session:
            stmt = select(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def get_all_users(self) -> list:
        """Получение всех пользователей"""
        async with self.async_session() as session:
            stmt = select(User.user_id)
            result = await session.execute(stmt)
            return [row[0] for row in result.fetchall()]

    # Методы для работы с балансом
    async def get_user_balance(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение баланса пользователя с использованием Cache-Aside паттерна"""
        # Сначала пытаемся получить из кеша
        if self.user_cache:
            cached_balance = await self.user_cache.get_user_balance(user_id)
            if cached_balance is not None:
                return {"user_id": user_id, "balance": cached_balance}

        # Если в кеше нет, получаем из базы данных
        async with self.async_session() as session:
            stmt = select(Balance).where(Balance.user_id == user_id)
            result = await session.execute(stmt)
            balance = result.scalar_one_or_none()

            if balance:
                balance_data = {
                    "user_id": user_id,
                    "balance": float(balance.amount),
                    "currency": balance.currency,
                    "updated_at": balance.updated_at.isoformat() if balance.updated_at else None
                }

                # Кешируем результат
                if self.user_cache:
                    await self.user_cache.cache_user_balance(user_id, int(balance.amount))

                return balance_data
            else:
                # Если баланса нет, создаем его
                await self.create_user_balance(user_id, 0)
                return {"user_id": user_id, "balance": 0, "currency": "TON", "updated_at": None}

    async def create_user_balance(self, user_id: int, initial_amount: float = 0.0) -> bool:
        """Создание баланса для пользователя"""
        async with self.async_session() as session:
            try:
                # Проверяем, существует ли уже баланс
                existing_balance = await session.get(Balance, user_id)
                if existing_balance:
                    return True

                stmt = insert(Balance).values(
                    user_id=user_id,
                    amount=initial_amount,
                    currency="TON"
                )
                await session.execute(stmt)
                await session.commit()

                # Инвалидируем кеш пользователя
                if self.user_cache:
                    await self.user_cache.invalidate_user_cache(user_id)

                return True
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error creating balance for user {user_id}: {e}")
                return False

    async def update_user_balance(self, user_id: int, amount: float, operation: str = "add") -> bool:
        """Обновление баланса пользователя"""
        async with self.async_session() as session:
            try:
                # Получаем текущий баланс
                balance = await session.get(Balance, user_id)
                if not balance:
                    await self.create_user_balance(user_id, 0)
                    balance = await session.get(Balance, user_id)

                # Выполняем операцию
                if operation == "add":
                    balance.amount += amount
                elif operation == "subtract":
                    balance.amount -= amount
                elif operation == "set":
                    balance.amount = amount
                else:
                    raise ValueError(f"Unknown operation: {operation}")

                balance.updated_at = datetime.utcnow()
                await session.commit()

                # Инвалидируем кеш пользователя
                if self.user_cache:
                    await self.user_cache.update_user_balance(user_id, int(balance.amount))

                return True
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error updating balance for user {user_id}: {e}")
                return False

    async def create_transaction(self, user_id: int, transaction_type: TransactionType,
                                amount: float, status: TransactionStatus = TransactionStatus.PENDING,
                                description: Optional[str] = None, external_id: Optional[str] = None,
                                metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """Создание транзакции"""
        async with self.async_session() as session:
            try:
                # Преобразуем метаданные в JSON строку
                metadata_json = json.dumps(metadata) if metadata else None

                stmt = insert(Transaction).values(
                    user_id=user_id,
                    transaction_type=transaction_type,
                    status=status,
                    amount=amount,
                    description=description,
                    external_id=external_id,
                    transaction_metadata=metadata_json
                )
                result = await session.execute(stmt)
                await session.commit()

                # Инвалидируем кеш пользователя
                if self.user_cache:
                    await self.user_cache.invalidate_user_cache(user_id)

                return result.inserted_primary_key[0] if result.inserted_primary_key else None
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error creating transaction for user {user_id}: {e}")
                return None

    async def get_user_transactions(self, user_id: int, limit: int = 50,
                                   transaction_type: Optional[TransactionType] = None,
                                   status: Optional[TransactionStatus] = None) -> list:
        """Получение транзакций пользователя"""
        async with self.async_session() as session:
            stmt = select(Transaction).where(Transaction.user_id == user_id)

            if transaction_type:
                stmt = stmt.where(Transaction.transaction_type == transaction_type)
            if status:
                stmt = stmt.where(Transaction.status == status)

            stmt = stmt.order_by(Transaction.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            transactions = result.scalars().all()

            # Преобразуем в словари и парсим метаданные
            transactions_data = []
            for transaction in transactions:
                transaction_data = {
                    "id": transaction.id,
                    "user_id": transaction.user_id,
                    "transaction_type": transaction.transaction_type.value,
                    "status": transaction.status.value,
                    "amount": float(transaction.amount),
                    "currency": transaction.currency,
                    "description": transaction.description,
                    "external_id": transaction.external_id,
                    "created_at": transaction.created_at.isoformat() if transaction.created_at else None,
                    "updated_at": transaction.updated_at.isoformat() if transaction.updated_at else None
                }

                # Парсим метаданные
                if transaction.transaction_metadata:
                    try:
                        transaction_data["metadata"] = json.loads(transaction.transaction_metadata)
                    except json.JSONDecodeError:
                        transaction_data["metadata"] = transaction.transaction_metadata

                transactions_data.append(transaction_data)

            return transactions_data

    async def get_transaction_by_external_id(self, external_id: str) -> Optional[Dict[str, Any]]:
        """Получение транзакции по внешнему ID"""
        async with self.async_session() as session:
            stmt = select(Transaction).where(Transaction.external_id == external_id)
            result = await session.execute(stmt)
            transaction = result.scalar_one_or_none()

            if transaction:
                transaction_data = {
                    "id": transaction.id,
                    "user_id": transaction.user_id,
                    "transaction_type": transaction.transaction_type.value,
                    "status": transaction.status.value,
                    "amount": float(transaction.amount),
                    "currency": transaction.currency,
                    "description": transaction.description,
                    "external_id": transaction.external_id,
                    "created_at": transaction.created_at.isoformat() if transaction.created_at else None,
                    "updated_at": transaction.updated_at.isoformat() if transaction.updated_at else None
                }

                # Парсим метаданные
                if transaction.transaction_metadata:
                    try:
                        transaction_data["metadata"] = json.loads(transaction.transaction_metadata)
                    except json.JSONDecodeError:
                        transaction_data["metadata"] = transaction.transaction_metadata

                return transaction_data

            return None

    async def update_transaction_status(self, transaction_id: int, status: TransactionStatus,
                                      metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Обновление статуса транзакции"""
        async with self.async_session() as session:
            try:
                transaction = await session.get(Transaction, transaction_id)
                if not transaction:
                    return False

                transaction.status = status
                transaction.updated_at = datetime.utcnow()

                if metadata:
                    transaction.transaction_metadata = json.dumps(metadata)

                await session.commit()

                # Если транзакция завершена, обновляем баланс
                if status == TransactionStatus.COMPLETED:
                    user_id = transaction.user_id
                    if transaction.transaction_type == TransactionType.PURCHASE:
                        # Для покупок вычитаем сумму
                        await self.update_user_balance(user_id, float(transaction.amount), "subtract")
                    elif transaction.transaction_type == TransactionType.REFUND:
                        # Для возвратов добавляем сумму
                        await self.update_user_balance(user_id, float(transaction.amount), "add")
                    elif transaction.transaction_type == TransactionType.BONUS:
                        # Для бонусов добавляем сумму
                        await self.update_user_balance(user_id, float(transaction.amount), "add")

                return True
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error updating transaction {transaction_id}: {e}")
                return False
