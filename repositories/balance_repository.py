"""
Репозиторий для работы с балансом и транзакциями через PostgreSQL
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, insert, update, delete, func
from sqlalchemy.exc import IntegrityError

from repositories.user_repository import Balance, Transaction, TransactionType, TransactionStatus


class BalanceRepository:
    """Репозиторий для управления балансом и транзакциями"""

    def __init__(self, async_session: sessionmaker):
        self.async_session = async_session
        self.logger = logging.getLogger(__name__)

    async def get_user_balance(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение баланса пользователя"""
        async with self.async_session() as session:
            try:
                stmt = select(Balance).where(Balance.user_id == user_id)
                result = await session.execute(stmt)
                balance = result.scalar_one_or_none()

                if balance:
                    return {
                        "user_id": user_id,
                        "balance": float(balance.amount),
                        "currency": balance.currency,
                        "updated_at": balance.updated_at.isoformat() if balance.updated_at else None,
                        "created_at": balance.created_at.isoformat() if balance.created_at else None
                    }
                else:
                    return None
            except Exception as e:
                self.logger.error(f"Error getting balance for user {user_id}: {e}")
                return None

    async def create_user_balance(self, user_id: int, initial_amount: float = 0.0, currency: str = "TON") -> bool:
        """Создание баланса для пользователя"""
        async with self.async_session() as session:
            try:
                # Проверяем, существует ли уже баланс
                existing_balance = await session.get(Balance, user_id)
                if existing_balance:
                    return True

                from decimal import Decimal
                stmt = insert(Balance).values(
                    user_id=user_id,
                    amount=Decimal(str(initial_amount)),
                    currency=currency
                )
                await session.execute(stmt)
                await session.commit()
                return True
            except IntegrityError as e:
                await session.rollback()
                self.logger.error(f"Balance already exists for user {user_id}: {e}")
                return False
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error creating balance for user {user_id}: {e}")
                return False

    async def update_user_balance(self, user_id: int, amount: float, operation: str = "add",
                                 currency: str = "TON") -> bool:
        """Обновление баланса пользователя"""
        async with self.async_session() as session:
            try:
                # Получаем текущий баланс
                stmt = select(Balance).where(Balance.user_id == user_id)
                result = await session.execute(stmt)
                balance = result.scalar_one_or_none()

                if not balance:
                    # Если баланса нет, создаем его
                    await self.create_user_balance(user_id, amount if operation == "set" else 0, currency)
                    balance = await session.get(Balance, user_id)

                # Выполняем операцию (преобразуем float в Decimal для совместимости)
                from decimal import Decimal
                amount_decimal = Decimal(str(amount))
                
                if operation == "add":
                    balance.amount += amount_decimal
                elif operation == "subtract":
                    balance.amount -= amount_decimal
                elif operation == "set":
                    balance.amount = amount_decimal
                else:
                    raise ValueError(f"Unknown operation: {operation}")

                balance.updated_at = datetime.utcnow()
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error updating balance for user {user_id}: {e}")
                return False

    async def create_transaction(self, user_id: int, transaction_type: TransactionType,
                                amount: float, status: TransactionStatus = TransactionStatus.PENDING,
                                description: Optional[str] = None, external_id: Optional[str] = None,
                                metadata: Optional[Dict[str, Any]] = None, currency: str = "TON") -> Optional[int]:
        """Создание транзакции"""
        async with self.async_session() as session:
            try:
                # Преобразуем метаданные в JSON строку
                metadata_json = json.dumps(metadata) if metadata else None

                from decimal import Decimal
                stmt = insert(Transaction).values(
                    user_id=user_id,
                    transaction_type=transaction_type,
                    status=status,
                    amount=Decimal(str(amount)),
                    currency=currency,
                    description=description,
                    external_id=external_id,
                    transaction_metadata=metadata_json
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.inserted_primary_key[0] if result.inserted_primary_key else None
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error creating transaction for user {user_id}: {e}")
                return None

    async def get_user_transactions(self, user_id: int, limit: int = 50,
                                   transaction_type: Optional[TransactionType] = None,
                                   status: Optional[TransactionStatus] = None,
                                   offset: int = 0) -> List[Dict[str, Any]]:
        """Получение транзакций пользователя"""
        async with self.async_session() as session:
            try:
                stmt = select(Transaction).where(Transaction.user_id == user_id)

                if transaction_type:
                    stmt = stmt.where(Transaction.transaction_type == transaction_type)
                if status:
                    stmt = stmt.where(Transaction.status == status)

                stmt = stmt.order_by(Transaction.created_at.desc()).offset(offset).limit(limit)
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
                            # Убираем избыточное логирование - логируем только ошибки
                        except json.JSONDecodeError as e:
                            self.logger.warning(f"Failed to parse metadata for transaction {transaction.id}: {e}")
                            transaction_data["metadata"] = transaction.transaction_metadata
                        except Exception as e:
                            self.logger.error(f"Unexpected error parsing metadata for transaction {transaction.id}: {e}")
                            transaction_data["metadata"] = transaction.transaction_metadata
                    else:
                        transaction_data["metadata"] = None

                    transactions_data.append(transaction_data)

                return transactions_data
            except Exception as e:
                self.logger.error(f"Error getting transactions for user {user_id}: {e}")
                return []

    async def get_transaction_by_external_id(self, external_id: str) -> Optional[Dict[str, Any]]:
        """Получение транзакции по внешнему ID"""
        async with self.async_session() as session:
            try:
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
                            # Убираем избыточное логирование
                        except json.JSONDecodeError as e:
                            self.logger.warning(f"Failed to parse metadata for transaction {transaction.id} by external_id: {e}")
                            transaction_data["metadata"] = transaction.transaction_metadata
                        except Exception as e:
                            self.logger.error(f"Unexpected error parsing metadata for transaction {transaction.id} by external_id: {e}")
                            transaction_data["metadata"] = transaction.transaction_metadata
                    else:
                        transaction_data["metadata"] = None

                    return transaction_data

                return None
            except Exception as e:
                self.logger.error(f"Error getting transaction by external_id {external_id}: {e}")
                return None

    async def update_transaction_status(self, transaction_id: int, status: TransactionStatus,
                                      metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Обновление статуса транзакции"""
        async with self.async_session() as session:
            try:
                stmt = select(Transaction).where(Transaction.id == transaction_id)
                result = await session.execute(stmt)
                transaction = result.scalar_one_or_none()

                if not transaction:
                    return False

                # Обновляем транзакцию
                update_stmt = update(Transaction).where(Transaction.id == transaction_id).values(
                    status=status,
                    updated_at=datetime.utcnow()
                )

                if metadata:
                    update_stmt = update_stmt.values(transaction_metadata=json.dumps(metadata))

                await session.execute(update_stmt)
                await session.commit()

                # Если транзакция завершена, обновляем баланс
                if status == TransactionStatus.COMPLETED:
                    user_id = transaction.user_id
                    if transaction.transaction_type == TransactionType.PURCHASE:
                        # Для покупок вычитаем сумму
                        await self.update_user_balance(user_id, float(transaction.amount), "subtract", transaction.currency)
                    elif transaction.transaction_type == TransactionType.REFUND:
                        # Для возвратов добавляем сумму
                        await self.update_user_balance(user_id, float(transaction.amount), "add", transaction.currency)
                    elif transaction.transaction_type == TransactionType.BONUS:
                        # Для бонусов добавляем сумму
                        await self.update_user_balance(user_id, float(transaction.amount), "add", transaction.currency)

                return True
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error updating transaction {transaction_id}: {e}")
                return False

    async def get_transaction_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики транзакций пользователя"""
        async with self.async_session() as session:
            try:
                # Общая статистика
                total_stmt = select(func.count(Transaction.id)).where(Transaction.user_id == user_id)
                total_result = await session.execute(total_stmt)
                total_count = total_result.scalar() or 0

                # Статистика по типам
                type_stats = {}
                for transaction_type in TransactionType:
                    count_stmt = select(func.count(Transaction.id)).where(
                        Transaction.user_id == user_id,
                        Transaction.transaction_type == transaction_type
                    )
                    count_result = await session.execute(count_stmt)
                    type_stats[transaction_type.value] = count_result.scalar() or 0

                # Статистика по статусам
                status_stats = {}
                for status in TransactionStatus:
                    count_stmt = select(func.count(Transaction.id)).where(
                        Transaction.user_id == user_id,
                        Transaction.status == status
                    )
                    count_result = await session.execute(count_stmt)
                    status_stats[status.value] = count_result.scalar() or 0

                # Общая сумма транзакций
                amount_stmt = select(func.sum(Transaction.amount)).where(Transaction.user_id == user_id)
                amount_result = await session.execute(amount_stmt)
                total_amount = float(amount_result.scalar() or 0)

                return {
                    "total_transactions": total_count,
                    "type_statistics": type_stats,
                    "status_statistics": status_stats,
                    "total_amount": total_amount
                }
            except Exception as e:
                self.logger.error(f"Error getting transaction statistics for user {user_id}: {e}")
                return {}

    async def delete_transaction(self, transaction_id: int) -> bool:
        """Удаление транзакции"""
        async with self.async_session() as session:
            try:
                stmt = delete(Transaction).where(Transaction.id == transaction_id)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error deleting transaction {transaction_id}: {e}")
                return False

    async def get_pending_transactions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение всех ожидающих обработки транзакций"""
        async with self.async_session() as session:
            try:
                stmt = select(Transaction).where(Transaction.status == TransactionStatus.PENDING)
                stmt = stmt.order_by(Transaction.created_at.asc()).limit(limit)
                result = await session.execute(stmt)
                transactions = result.scalars().all()

                # Преобразуем в словари
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
                            # Убираем избыточное логирование
                        except json.JSONDecodeError as e:
                            self.logger.warning(f"Failed to parse metadata for pending transaction {transaction.id}: {e}")
                            transaction_data["metadata"] = transaction.transaction_metadata
                        except Exception as e:
                            self.logger.error(f"Unexpected error parsing metadata for pending transaction {transaction.id}: {e}")
                            transaction_data["metadata"] = transaction.transaction_metadata
                    else:
                        transaction_data["metadata"] = None

                    transactions_data.append(transaction_data)

                return transactions_data
            except Exception as e:
                self.logger.error(f"Error getting pending transactions: {e}")
                return []


    async def check_balance_sufficiency(self, user_id: int, required_amount: float) -> bool:
        """Проверка достаточности баланса пользователя"""
        try:
            balance_data = await self.get_user_balance(user_id)
            if not balance_data:
                return False

            current_balance = float(balance_data["balance"])
            return current_balance >= required_amount
        except Exception as e:
            self.logger.error(f"Error checking balance sufficiency for user {user_id}: {e}")
            return False

    async def get_user_balance_with_transactions(self, user_id: int, limit: int = 50) -> Dict[str, Any]:
        """Получение баланса пользователя с последними транзакциями"""
        try:
            # Получаем баланс
            balance_data = await self.get_user_balance(user_id)
            if not balance_data:
                return {"balance": 0, "currency": "TON", "transactions": []}

            # Получаем последние транзакции
            transactions = await self.get_user_transactions(user_id, limit)

            return {
                "balance": balance_data["balance"],
                "currency": balance_data["currency"],
                "updated_at": balance_data["updated_at"],
                "transactions": transactions
            }
        except Exception as e:
            self.logger.error(f"Error getting balance with transactions for user {user_id}: {e}")
            return {"balance": 0, "currency": "TON", "transactions": []}

    async def cancel_transaction_and_refund(self, transaction_id: int) -> bool:
        """Отмена транзакции и возврат средств"""
        async with self.async_session() as session:
            try:
                # Получаем транзакцию
                stmt = select(Transaction).where(Transaction.id == transaction_id)
                result = await session.execute(stmt)
                transaction = result.scalar_one_or_none()

                if not transaction:
                    return False

                # Проверяем, можно ли отменить транзакцию
                if transaction.status != TransactionStatus.PENDING:
                    return False

                # Возвращаем средства на баланс
                if transaction.transaction_type == TransactionType.PURCHASE:
                    success = await self.update_user_balance(
                        transaction.user_id,
                        float(transaction.amount),
                        "add",
                        transaction.currency
                    )

                    if success:
                        # Обновляем статус транзакции
                        await self.update_transaction_status(
                            transaction_id,
                            TransactionStatus.CANCELLED,
                            metadata={
                                "cancelled_at": datetime.utcnow().isoformat(),
                                "cancelled_by": "system",
                                "refund_processed": True
                            }
                        )
                        return True

                return False
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Error cancelling transaction {transaction_id}: {e}")
                return False
