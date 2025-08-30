"""
Сервис для управления балансом пользователей с интеграцией кеширования
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from core.interfaces import BalanceServiceInterface
from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from repositories.user_repository import TransactionType, TransactionStatus
from services.cache.user_cache import UserCache


class BalanceService(BalanceServiceInterface):
    """Сервис для управления балансом пользователей с кешированием"""

    def __init__(self, user_repository: UserRepository, balance_repository: BalanceRepository,
                 user_cache: Optional[UserCache] = None):
        self.user_repository = user_repository
        self.balance_repository = balance_repository
        self.user_cache = user_cache
        self.logger = logging.getLogger(__name__)

    async def get_user_balance(self, user_id: int) -> Dict[str, Any]:
        """Получение баланса пользователя с использованием Cache-Aside паттерна"""
        # Сначала пытаемся получить из кеша
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

        # Если в кеше нет, получаем из базы данных
        balance_data = await self.balance_repository.get_user_balance(user_id)
        if balance_data:
            # Кешируем результат с увеличенным TTL
            if self.user_cache:
                await self.user_cache.cache_user_balance(user_id, int(balance_data["balance"]))

            balance_data["source"] = "database"
            return balance_data
        else:
            # Если баланса нет, создаем его и сразу кешируем
            await self.balance_repository.create_user_balance(user_id, 0)
            
            # Кешируем нулевой баланс для новых пользователей
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
        """Обновление баланса пользователя с кешированием"""
        try:
            # Выполняем операцию
            success = await self.balance_repository.update_user_balance(user_id, amount, operation)

            if success and self.user_cache:
                # Получаем обновленный баланс
                balance_data = await self.balance_repository.get_user_balance(user_id)
                if balance_data:
                    # Обновляем кеш
                    await self.user_cache.update_user_balance(user_id, int(balance_data["balance"]))

            return success
        except Exception as e:
            self.logger.error(f"Error updating balance for user {user_id}: {e}")
            return False

    async def get_user_transactions(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Получение транзакций пользователя"""
        try:
            return await self.balance_repository.get_user_transactions(user_id, limit)
        except Exception as e:
            self.logger.error(f"Error getting transactions for user {user_id}: {e}")
            return []

    async def create_transaction(self, user_id: int, transaction_type: str, amount: float,
                                description: Optional[str] = None, external_id: Optional[str] = None,
                                metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """Создание транзакции"""
        try:
            # Валидация типа транзакции
            try:
                transaction_enum = TransactionType(transaction_type.lower())
            except ValueError:
                self.logger.error(f"Invalid transaction type: {transaction_type}")
                return None

            # Создаем транзакцию
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
                # Инвалидируем кеш пользователя
                await self.user_cache.invalidate_user_cache(user_id)

            return transaction_id
        except Exception as e:
            self.logger.error(f"Error creating transaction for user {user_id}: {e}")
            return None

    async def complete_transaction(self, transaction_id: int, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Завершение транзакции"""
        try:
            success = await self.balance_repository.update_transaction_status(
                transaction_id=transaction_id,
                status=TransactionStatus.COMPLETED,
                metadata=metadata
            )

            if success and self.user_cache:
                # Получаем пользователя для инвалидации кеша
                transaction_data = await self.balance_repository.get_transaction_by_external_id(
                    f"transaction_{transaction_id}"
                )
                if transaction_data:
                    await self.user_cache.invalidate_user_cache(transaction_data["user_id"])

            return success
        except Exception as e:
            self.logger.error(f"Error completing transaction {transaction_id}: {e}")
            return False

    async def fail_transaction(self, transaction_id: int, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Отмена транзакции с ошибкой"""
        try:
            success = await self.balance_repository.update_transaction_status(
                transaction_id=transaction_id,
                status=TransactionStatus.FAILED,
                metadata=metadata
            )

            if success and self.user_cache:
                # Получаем пользователя для инвалидации кеша
                transaction_data = await self.balance_repository.get_transaction_by_external_id(
                    f"transaction_{transaction_id}"
                )
                if transaction_data:
                    await self.user_cache.invalidate_user_cache(transaction_data["user_id"])

            return success
        except Exception as e:
            self.logger.error(f"Error failing transaction {transaction_id}: {e}")
            return False

    async def get_transaction_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики транзакций пользователя"""
        try:
            return await self.balance_repository.get_transaction_statistics(user_id)
        except Exception as e:
            self.logger.error(f"Error getting transaction statistics for user {user_id}: {e}")
            return {}

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

    async def get_pending_transactions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение всех ожидающих обработки транзакций"""
        try:
            return await self.balance_repository.get_pending_transactions(limit)
        except Exception as e:
            self.logger.error(f"Error getting pending transactions: {e}")
            return []

    async def validate_transaction_amount(self, amount: float) -> bool:
        """Валидация суммы транзакции"""
        try:
            if amount <= 0:
                return False

            # Можно добавить дополнительные проверки, например, максимальную сумму
            if amount > 1000000:  # 1,000,000 TON
                return False

            return True
        except Exception as e:
            self.logger.error(f"Error validating transaction amount {amount}: {e}")
            return False

    async def get_user_balance_history(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Получение истории баланса пользователя за указанный период"""
        try:
            from datetime import timedelta

            # Вычисляем дату начала периода
            start_date = datetime.utcnow() - timedelta(days=days)

            # Получаем транзакции за период
            transactions = await self.balance_repository.get_user_transactions(
                user_id=user_id,
                limit=1000  # Ограничиваем количество для производительности
            )

            # Фильтруем по дате
            filtered_transactions = [
                t for t in transactions
                if t.get("created_at") and datetime.fromisoformat(t["created_at"]) >= start_date
            ]

            # Вычисляем начальный баланс (самая ранняя транзакция)
            if filtered_transactions:
                earliest_transaction = min(
                    filtered_transactions,
                    key=lambda x: x.get("created_at", "")
                )
                # Здесь можно добавить логику вычисления начального баланса
                initial_balance = 0  # Упрощено для примера
            else:
                initial_balance = 0

            # Получаем реальный текущий баланс из базы данных
            current_balance_data = await self.get_user_balance(user_id)
            final_balance = current_balance_data.get("balance", 0) if current_balance_data else 0
            
            # Вычисляем начальный баланс на основе текущего и транзакций
            # Начальный баланс = текущий баланс - сумма всех завершенных транзакций за период
            balance_change = 0
            for transaction in filtered_transactions:
                # Учитываем только завершенные транзакции для расчета изменения баланса
                if transaction.get("status") == "completed":
                    if transaction["transaction_type"] == "purchase":
                        balance_change -= transaction["amount"]
                    elif transaction["transaction_type"] in ["refund", "bonus", "recharge"]:
                        balance_change += transaction["amount"]
            
            # Начальный баланс = текущий баланс - изменения за период
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

    async def process_recharge(self, user_id: int, amount: float, payment_uuid: str) -> bool:
        """Обработка пополнения баланса после успешного платежа с транзакционной безопасностью"""
        try:
            # Валидация суммы
            if not await self.validate_transaction_amount(amount):
                self.logger.error(f"Invalid recharge amount: {amount} for user {user_id}")
                return False

            # Проверяем, не была ли транзакция уже обработана
            existing_transaction = await self.balance_repository.get_transaction_by_external_id(payment_uuid)
            if existing_transaction and existing_transaction["status"] == TransactionStatus.COMPLETED.value:
                self.logger.warning(f"Duplicate recharge transaction detected: {payment_uuid}")
                return True

            # Создаем новую транзакцию если не найдена
            if not existing_transaction:
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
                transaction_id = existing_transaction["id"]

            if not transaction_id:
                self.logger.error(f"Failed to create transaction for recharge {payment_uuid}")
                return False

            # Транзакционное обновление баланса и статуса
            try:
                # Обновляем баланс
                update_success = await self.balance_repository.update_user_balance(user_id, amount, "add")
                
                if update_success:
                    # Принудительно инвалидируем кэш пользователя, чтобы гарантировать свежесть данных
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
                    
            except Exception as inner_e:
                self.logger.error(f"Error during transaction processing for recharge {payment_uuid}: {inner_e}")
                # Отмечаем транзакцию как failed
                await self.fail_transaction(
                    transaction_id,
                    metadata={
                        "failed_at": datetime.utcnow().isoformat(),
                        "error": f"Processing error: {str(inner_e)}",
                        "payment_uuid": payment_uuid
                    }
                )
                return False

        except Exception as e:
            self.logger.error(f"Error processing recharge {payment_uuid} for user {user_id}: {e}")
            return False

    async def get_recharge_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение истории пополнений баланса пользователя"""
        try:
            # Получаем транзакции типа recharge
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


    async def check_balance_sufficiency(self, user_id: int, required_amount: float) -> bool:
        """Проверка достаточности баланса пользователя"""
        try:
            balance_data = await self.balance_repository.get_user_balance(user_id)
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
            balance_data = await self.balance_repository.get_user_balance_with_transactions(user_id, limit)
            return balance_data
        except Exception as e:
            self.logger.error(f"Error getting balance with transactions for user {user_id}: {e}")
            return {"balance": 0, "currency": "TON", "transactions": []}

    async def cancel_transaction_and_refund(self, transaction_id: int) -> bool:
        """Отмена транзакции и возврат средств"""
        try:
            return await self.balance_repository.cancel_transaction_and_refund(transaction_id)
        except Exception as e:
            self.logger.error(f"Error cancelling transaction {transaction_id}: {e}")
            return False

    async def get_purchase_history_with_balance(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        """Получение истории покупок с информацией о балансе"""
        try:
            # Получаем баланс
            balance_data = await self.get_user_balance(user_id)
            current_balance = balance_data.get("balance", 0) if balance_data else 0

            # Получаем историю покупок
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
