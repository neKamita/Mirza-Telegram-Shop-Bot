"""
BalanceService - рефакторированный сервис для управления балансом пользователей

🎯 Основные возможности:
- Оркестрация специализированных компонентов
- Сохранение обратной совместимости
- Улучшенная архитектура с SOLID принципами
- Централизованное управление балансом

📊 Архитектура:
- Использует BalanceManager для управления балансом
- Использует TransactionManager для транзакций
- Использует BalanceFormatter для форматирования
- Сохраняет единый интерфейс для обратной совместимости

🔧 Рефакторинг:
- Разделение ответственности по компонентам
- Улучшение тестируемости
- Снижение технического долга
- Сохранение всех функций
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from .balance_manager import BalanceManager
from .transaction_manager import TransactionManager
from .balance_formatter import BalanceFormatter
from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from services.cache import UserCache
from utils.message_formatter import MessageFormatter


class BalanceService:
    """
    Рефакторированный сервис управления балансом пользователей

    🚀 Новые принципы:
    - Оркестрация компонентов вместо монолитной реализации
    - Четкое разделение ответственности
    - Улучшенная тестируемость
    - Сохранение обратной совместимости
    """

    def __init__(self,
                 user_repository: UserRepository,
                 balance_repository: BalanceRepository,
                 user_cache: Optional[UserCache] = None,
                 message_formatter: Optional[MessageFormatter] = None):
        """
        Args:
            user_repository: Репозиторий пользователей
            balance_repository: Репозиторий баланса
            user_cache: Опциональный кеш пользователей
            message_formatter: Опциональный форматтер сообщений
        """
        self.user_repository = user_repository
        self.balance_repository = balance_repository
        self.user_cache = user_cache
        self.message_formatter = message_formatter
        self.logger = logging.getLogger(__name__)

        # Инициализация компонентов
        self.balance_manager = BalanceManager(balance_repository, user_cache)
        self.transaction_manager = TransactionManager(balance_repository, user_cache)
        self.balance_formatter = BalanceFormatter(message_formatter)

    # Делегирование методов BalanceManager
    async def get_user_balance(self, user_id: int) -> Dict[str, Any]:
        """Получение баланса пользователя"""
        return await self.balance_manager.get_user_balance(user_id)

    async def update_user_balance(self, user_id: int, amount: float, operation: str = "add") -> bool:
        """Обновление баланса пользователя"""
        return await self.balance_manager.update_user_balance(user_id, amount, operation)

    async def check_balance_sufficiency(self, user_id: int, required_amount: float) -> bool:
        """Проверка достаточности баланса"""
        return await self.balance_manager.check_balance_sufficiency(user_id, required_amount)

    async def get_balance_with_transactions(self, user_id: int, limit: int = 50) -> Dict[str, Any]:
        """Получение баланса с транзакциями"""
        return await self.balance_manager.get_balance_with_transactions(user_id, limit)

    # Делегирование методов TransactionManager
    async def create_transaction(self, user_id: int, transaction_type: str, amount: float,
                                 description: Optional[str] = None, external_id: Optional[str] = None,
                                 metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """Создание транзакции"""
        return await self.transaction_manager.create_transaction(
            user_id, transaction_type, amount, description, external_id, metadata
        )

    async def complete_transaction(self, transaction_id: int, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Завершение транзакции"""
        return await self.transaction_manager.complete_transaction(transaction_id, metadata)

    async def fail_transaction(self, transaction_id: int, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Отмена транзакции с ошибкой"""
        return await self.transaction_manager.fail_transaction(transaction_id, metadata)

    async def get_user_transactions(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Получение транзакций пользователя"""
        return await self.transaction_manager.get_user_transactions(user_id, limit)

    async def get_transaction_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики транзакций"""
        return await self.transaction_manager.get_transaction_statistics(user_id)

    async def get_pending_transactions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение ожидающих транзакций"""
        return await self.transaction_manager.get_pending_transactions(limit)

    async def cancel_transaction_and_refund(self, transaction_id: int) -> bool:
        """Отмена транзакции и возврат средств"""
        return await self.transaction_manager.cancel_transaction_and_refund(transaction_id)

    async def validate_transaction_amount(self, amount: float) -> bool:
        """Валидация суммы транзакции"""
        return await self.transaction_manager.validate_transaction_amount(amount)

    # Делегирование методов BalanceFormatter
    async def get_balance_message(self, user_id: int) -> str:
        """Получение отформатированного сообщения баланса"""
        balance_data = await self.get_user_balance(user_id)
        return await self.balance_formatter.get_balance_message(user_id, balance_data)

    async def get_transaction_history_message(self, user_id: int, days: int = 30) -> str:
        """Получение отформатированного сообщения истории транзакций"""
        # Получаем историю баланса с транзакциями
        balance_history = await self.get_user_balance_history(user_id, days)
        return await self.balance_formatter.get_transaction_history_message(user_id, balance_history, days)

    # Сложные методы, требующие координации компонентов
    async def process_recharge(self, user_id: int, amount: float, payment_uuid: str) -> bool:
        """Обработка пополнения баланса после успешного платежа"""
        try:
            # Валидация суммы
            if not await self.validate_transaction_amount(amount):
                self.logger.error(f"Invalid recharge amount: {amount} for user {user_id}")
                return False

            # Получаем транзакцию по UUID платежа
            transaction_data = await self.balance_repository.get_transaction_by_external_id(payment_uuid)
            if not transaction_data:
                # Создаем новую транзакцию
                transaction_id = await self.create_transaction(
                    user_id=user_id,
                    transaction_type="recharge",
                    amount=amount,
                    description="Пополнение баланса",
                    external_id=payment_uuid,
                    metadata={
                        "payment_uuid": payment_uuid,
                        "recharge_type": "heleket",
                        "processed_at": datetime.utcnow().isoformat()
                    }
                )
            else:
                transaction_id = transaction_data["id"]

            if not transaction_id:
                self.logger.error(f"Failed to create transaction for recharge {payment_uuid}")
                return False

            # Обновляем баланс
            success = await self.update_user_balance(user_id, amount, "add")
            if success:
                # Принудительно инвалидируем кеш пользователя
                if self.user_cache:
                    await self.user_cache.invalidate_user_cache(user_id)
                    self.logger.info(f"Invalidated user cache for {user_id} after recharge")

                # Завершаем транзакцию
                await self.complete_transaction(
                    transaction_id,
                    metadata={
                        "completed_at": datetime.utcnow().isoformat(),
                        "payment_uuid": payment_uuid,
                        "balance_updated": True,
                        "cache_invalidated": True
                    }
                )
                self.logger.info(f"Successfully processed recharge {payment_uuid} for user {user_id}")
                return True
            else:
                # Отмечаем транзакцию как failed
                await self.fail_transaction(
                    transaction_id,
                    metadata={
                        "failed_at": datetime.utcnow().isoformat(),
                        "error": "Failed to update balance",
                        "payment_uuid": payment_uuid
                    }
                )
                self.logger.error(f"Failed to update balance for recharge {payment_uuid}")
                return False

        except Exception as e:
            self.logger.error(f"Error processing recharge {payment_uuid} for user {user_id}: {e}")
            return False

    async def get_user_balance_history(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Получение истории баланса пользователя за указанный период"""
        try:
            from datetime import timedelta

            # Вычисляем дату начала периода
            start_date = datetime.utcnow() - timedelta(days=days)

            # Получаем транзакции за период
            transactions = await self.get_user_transactions(user_id, limit=1000)

            # Фильтруем по дате
            filtered_transactions = [
                t for t in transactions
                if t.get("created_at") and datetime.fromisoformat(t["created_at"]) >= start_date
            ]

            # Вычисляем начальный баланс
            if filtered_transactions:
                earliest_transaction = min(
                    filtered_transactions,
                    key=lambda x: x.get("created_at", "")
                )
                initial_balance = 0  # Упрощено
            else:
                initial_balance = 0

            # Получаем текущий баланс
            current_balance_data = await self.get_user_balance(user_id)
            final_balance = current_balance_data.get("balance", 0) if current_balance_data else 0

            # Вычисляем начальный баланс на основе текущего и транзакций
            balance_change = 0
            for transaction in filtered_transactions:
                if transaction.get("status") == "completed":
                    if transaction["transaction_type"] == "purchase":
                        balance_change -= transaction["amount"]
                    elif transaction["transaction_type"] in ["refund", "bonus", "recharge"]:
                        balance_change += transaction["amount"]

            initial_balance = final_balance - balance_change

            return {
                "user_id": user_id,
                "period_days": days,
                "initial_balance": initial_balance,
                "final_balance": final_balance,
                "transactions_count": len(filtered_transactions),
                "transactions": filtered_transactions
            }

        except Exception as e:
            self.logger.error(f"Error getting balance history for user {user_id}: {e}")
            return {}

    async def get_recharge_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение истории пополнений баланса пользователя"""
        try:
            from repositories.user_repository import TransactionType
            transactions = await self.balance_repository.get_user_transactions(
                user_id=user_id,
                limit=limit,
                transaction_type=TransactionType.RECHARGE
            )

            # Форматируем данные для удобства
            recharge_history = []
            for transaction in transactions:
                recharge_data = {
                    "id": transaction["id"],
                    "amount": transaction["amount"],
                    "currency": transaction["currency"],
                    "status": transaction["status"],
                    "created_at": transaction["created_at"],
                    "description": transaction["description"],
                    "payment_uuid": transaction.get("metadata", {}).get("payment_uuid"),
                    "completed_at": transaction.get("metadata", {}).get("completed_at")
                }
                recharge_history.append(recharge_data)

            return recharge_history

        except Exception as e:
            self.logger.error(f"Error getting recharge history for user {user_id}: {e}")
            return []

    async def get_purchase_history_with_balance(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        """Получение истории покупок с информацией о балансе"""
        try:
            # Получаем баланс
            balance_data = await self.get_user_balance(user_id)
            current_balance = balance_data.get("balance", 0) if balance_data else 0

            # Получаем историю покупок
            from repositories.user_repository import TransactionType
            purchase_history = await self.balance_repository.get_user_transactions(
                user_id=user_id,
                limit=limit,
                transaction_type=TransactionType.PURCHASE
            )

            # Получаем статистику покупок
            purchase_stats = await self.get_transaction_statistics(user_id)

            return {
                "current_balance": current_balance,
                "currency": "TON",
                "purchase_history": purchase_history,
                "purchase_statistics": purchase_stats,
                "total_purchases": len(purchase_history)
            }

        except Exception as e:
            self.logger.error(f"Error getting purchase history with balance for user {user_id}: {e}")
            return {
                "current_balance": 0,
                "currency": "TON",
                "purchase_history": [],
                "purchase_statistics": {},
                "total_purchases": 0
            }

    async def add_bonus(self, user_id: int, amount: float, description: Optional[str] = None,
                        metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Бонусное начисление пользователю"""
        try:
            # Создаем транзакцию бонуса
            transaction_id = await self.create_transaction(
                user_id=user_id,
                transaction_type="bonus",
                amount=amount,
                description=description or "Бонусное начисление",
                metadata=metadata
            )

            if transaction_id:
                # Завершаем транзакцию
                return await self.complete_transaction(
                    transaction_id,
                    metadata={"completed_at": datetime.utcnow().isoformat()}
                )

            return False

        except Exception as e:
            self.logger.error(f"Error adding bonus to user {user_id}: {e}")
            return False

    async def process_refund(self, user_id: int, amount: float, description: Optional[str] = None,
                            external_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Обработка возврата пользователю"""
        try:
            # Создаем транзакцию возврата
            transaction_id = await self.create_transaction(
                user_id=user_id,
                transaction_type="refund",
                amount=amount,
                description=description or "Возврат средств",
                external_id=external_id,
                metadata=metadata
            )

            if transaction_id:
                # Завершаем транзакцию
                return await self.complete_transaction(
                    transaction_id,
                    metadata={"completed_at": datetime.utcnow().isoformat()}
                )

            return False

        except Exception as e:
            self.logger.error(f"Error processing refund for user {user_id}: {e}")
            return False

    async def invalidate_user_sessions(self, user_id: int, keep_active: bool = False) -> int:
        """Инвалидация сессий пользователя (для обратной совместимости)"""
        try:
            # Этот метод больше не относится к BalanceService
            # но сохраняется для обратной совместимости
            self.logger.warning(f"BalanceService.invalidate_user_sessions called for user {user_id} - consider using SessionCache")
            return 0
        except Exception as e:
            self.logger.error(f"Error in invalidate_user_sessions for user {user_id}: {e}")
            return 0