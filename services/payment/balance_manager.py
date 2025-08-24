"""
BalanceManager - специализированный сервис для управления балансом пользователей

🎯 Основные возможности:
- Управление балансом с кешированием
- Cache-Aside паттерн для производительности
- Graceful degradation при проблемах с кешем
- Оптимизированные операции чтения/записи

📊 Архитектура:
- Чистое разделение ответственности (SRP)
- Dependency Injection для тестируемости
- Опциональная интеграция с кешем
- Унифицированная обработка ошибок
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from repositories.balance_repository import BalanceRepository
from services.cache import UserCache


class BalanceManager:
    """
    Сервис управления балансом пользователей с кешированием

    🚀 Принципы:
    - Единая ответственность: только управление балансом
    - Опциональная зависимость от кеша
    - Чистые методы без бизнес-логики
    """

    def __init__(self,
                 balance_repository: BalanceRepository,
                 user_cache: Optional[UserCache] = None):
        """
        Args:
            balance_repository: Репозиторий для работы с балансом
            user_cache: Опциональный кеш пользователей
        """
        self.balance_repository = balance_repository
        self.user_cache = user_cache
        self.logger = logging.getLogger(f"{__name__}.BalanceManager")

    async def get_user_balance(self, user_id: int) -> Dict[str, Any]:
        """
        Получение баланса пользователя с кешированием

        Args:
            user_id: ID пользователя

        Returns:
            Данные баланса с источником
        """
        # Cache-Aside паттерн
        if self.user_cache:
            cached_balance = await self.user_cache.get_user_balance(user_id)
            if cached_balance is not None:
                return {
                    "user_id": user_id,
                    "balance": cached_balance,
                    "currency": "TON",
                    "updated_at": datetime.utcnow().isoformat(),
                    "source": "cache"
                }

        # Получение из базы данных
        balance_data = await self.balance_repository.get_user_balance(user_id)
        if balance_data:
            # Кешируем результат
            if self.user_cache:
                await self.user_cache.cache_user_balance(user_id, int(balance_data["balance"]))

            balance_data["source"] = "database"
            return balance_data
        else:
            # Создаем баланс для новых пользователей
            await self.balance_repository.create_user_balance(user_id, 0)

            # Кешируем нулевой баланс
            if self.user_cache:
                await self.user_cache.cache_user_balance(user_id, 0)

            return {
                "user_id": user_id,
                "balance": 0,
                "currency": "TON",
                "updated_at": datetime.utcnow().isoformat(),
                "source": "database"
            }

    async def update_user_balance(self, user_id: int, amount: float, operation: str = "add") -> bool:
        """
        Обновление баланса пользователя

        Args:
            user_id: ID пользователя
            amount: Сумма изменения
            operation: Тип операции (add/subtract)

        Returns:
            True если успешно обновлено
        """
        try:
            success = await self.balance_repository.update_user_balance(user_id, amount, operation)

            if success and self.user_cache:
                # Получаем обновленный баланс
                balance_data = await self.balance_repository.get_user_balance(user_id)
                if balance_data:
                    await self.user_cache.update_user_balance(user_id, int(balance_data["balance"]))

            return success

        except Exception as e:
            self.logger.error(f"Error updating balance for user {user_id}: {e}")
            return False

    async def check_balance_sufficiency(self, user_id: int, required_amount: float) -> bool:
        """
        Проверка достаточности баланса

        Args:
            user_id: ID пользователя
            required_amount: Требуемая сумма

        Returns:
            True если баланс достаточен
        """
        try:
            balance_data = await self.balance_repository.get_user_balance(user_id)
            if not balance_data:
                return False

            current_balance = float(balance_data["balance"])
            return current_balance >= required_amount

        except Exception as e:
            self.logger.error(f"Error checking balance sufficiency for user {user_id}: {e}")
            return False

    async def get_balance_with_transactions(self, user_id: int, limit: int = 50) -> Dict[str, Any]:
        """
        Получение баланса с последними транзакциями

        Args:
            user_id: ID пользователя
            limit: Максимальное количество транзакций

        Returns:
            Данные баланса с транзакциями
        """
        try:
            return await self.balance_repository.get_user_balance_with_transactions(user_id, limit)
        except Exception as e:
            self.logger.error(f"Error getting balance with transactions for user {user_id}: {e}")
            return {"balance": 0, "currency": "TON", "transactions": []}