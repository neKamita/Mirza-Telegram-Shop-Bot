"""
TransactionManager - специализированный сервис для управления транзакциями пользователей

🎯 Основные возможности:
- Создание и обработка транзакций всех типов
- Управление статусами транзакций
- Отмена и возврат транзакций
- Получение истории транзакций

📊 Архитектура:
- Чистое разделение ответственности (SRP)
- Единый интерфейс для всех типов транзакций
- Оптимизированные запросы с пагинацией
- Централизованная валидация
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from repositories.balance_repository import BalanceRepository
from repositories.user_repository import TransactionType, TransactionStatus
from services.cache import UserCache


class TransactionManager:
    """
    Сервис управления транзакциями пользователей

    🚀 Принципы:
    - Единая ответственность: только транзакции
    - Чистые методы без сайд-эффектов
    - Опциональная интеграция с кешем
    """

    def __init__(self,
                 balance_repository: BalanceRepository,
                 user_cache: Optional[UserCache] = None):
        """
        Args:
            balance_repository: Репозиторий для работы с балансом и транзакциями
            user_cache: Опциональный кеш пользователей
        """
        self.balance_repository = balance_repository
        self.user_cache = user_cache
        self.logger = logging.getLogger(f"{__name__}.TransactionManager")

    async def create_transaction(self,
                               user_id: int,
                               transaction_type: str,
                               amount: float,
                               description: Optional[str] = None,
                               external_id: Optional[str] = None,
                               metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """
        Создание новой транзакции

        Args:
            user_id: ID пользователя
            transaction_type: Тип транзакции
            amount: Сумма
            description: Описание
            external_id: Внешний ID
            metadata: Дополнительные данные

        Returns:
            ID созданной транзакции или None при ошибке
        """
        try:
            # Валидация типа транзакции
            try:
                transaction_enum = TransactionType(transaction_type.lower())
            except ValueError:
                self.logger.error(f"Invalid transaction type: {transaction_type}")
                return None

            # Создание транзакции
            transaction_id = await self.balance_repository.create_transaction(
                user_id=user_id,
                transaction_type=transaction_enum,
                amount=amount,
                status=TransactionStatus.PENDING,
                description=description,
                external_id=external_id,
                metadata=metadata
            )

            if transaction_id and self.user_cache:
                # Инвалидация кеша пользователя
                await self.user_cache.invalidate_user_cache(user_id)

            return transaction_id

        except Exception as e:
            self.logger.error(f"Error creating transaction for user {user_id}: {e}")
            return None

    async def complete_transaction(self,
                                 transaction_id: int,
                                 metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Завершение транзакции

        Args:
            transaction_id: ID транзакции
            metadata: Дополнительные данные

        Returns:
            True если успешно завершено
        """
        try:
            success = await self.balance_repository.update_transaction_status(
                transaction_id=transaction_id,
                status=TransactionStatus.COMPLETED,
                metadata=metadata
            )

            if success and self.user_cache:
                # Инвалидация кеша пользователя
                transaction_data = await self.balance_repository.get_transaction_by_external_id(
                    f"transaction_{transaction_id}"
                )
                if transaction_data:
                    await self.user_cache.invalidate_user_cache(transaction_data["user_id"])

            return success

        except Exception as e:
            self.logger.error(f"Error completing transaction {transaction_id}: {e}")
            return False

    async def fail_transaction(self,
                             transaction_id: int,
                             metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Отмена транзакции с ошибкой

        Args:
            transaction_id: ID транзакции
            metadata: Дополнительные данные

        Returns:
            True если успешно отменено
        """
        try:
            success = await self.balance_repository.update_transaction_status(
                transaction_id=transaction_id,
                status=TransactionStatus.FAILED,
                metadata=metadata
            )

            if success and self.user_cache:
                # Инвалидация кеша пользователя
                transaction_data = await self.balance_repository.get_transaction_by_external_id(
                    f"transaction_{transaction_id}"
                )
                if transaction_data:
                    await self.user_cache.invalidate_user_cache(transaction_data["user_id"])

            return success

        except Exception as e:
            self.logger.error(f"Error failing transaction {transaction_id}: {e}")
            return False

    async def get_user_transactions(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Получение транзакций пользователя

        Args:
            user_id: ID пользователя
            limit: Максимальное количество

        Returns:
            Список транзакций
        """
        try:
            return await self.balance_repository.get_user_transactions(user_id, limit)
        except Exception as e:
            self.logger.error(f"Error getting transactions for user {user_id}: {e}")
            return []

    async def get_transaction_statistics(self, user_id: int) -> Dict[str, Any]:
        """
        Получение статистики транзакций пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Статистика транзакций
        """
        try:
            return await self.balance_repository.get_transaction_statistics(user_id)
        except Exception as e:
            self.logger.error(f"Error getting transaction statistics for user {user_id}: {e}")
            return {}

    async def get_pending_transactions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Получение всех ожидающих обработки транзакций

        Args:
            limit: Максимальное количество

        Returns:
            Список ожидающих транзакций
        """
        try:
            return await self.balance_repository.get_pending_transactions(limit)
        except Exception as e:
            self.logger.error(f"Error getting pending transactions: {e}")
            return []

    async def cancel_transaction_and_refund(self, transaction_id: int) -> bool:
        """
        Отмена транзакции и возврат средств

        Args:
            transaction_id: ID транзакции

        Returns:
            True если успешно отменено и возвращено
        """
        try:
            return await self.balance_repository.cancel_transaction_and_refund(transaction_id)
        except Exception as e:
            self.logger.error(f"Error cancelling transaction {transaction_id}: {e}")
            return False

    async def validate_transaction_amount(self, amount: float) -> bool:
        """
        Валидация суммы транзакции

        Args:
            amount: Сумма для проверки

        Returns:
            True если сумма валидна
        """
        try:
            if amount <= 0:
                return False

            # Дополнительные проверки
            if amount > 1000000:  # 1,000,000 TON
                return False

            return True

        except Exception as e:
            self.logger.error(f"Error validating transaction amount {amount}: {e}")
            return False