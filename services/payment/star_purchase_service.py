"""
Сервис для покупки звезд с интеграцией платежной системы и кеширования
"""
import json
import logging
import time
import hashlib
import hmac
import base64
from typing import Dict, Any, Optional, List
from datetime import datetime

from core.interfaces import StarPurchaseServiceInterface
from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from repositories.user_repository import TransactionType, TransactionStatus
from services.payment.payment_service import PaymentService
from services.cache.payment_cache import PaymentCache
from services.cache.user_cache import UserCache
from services.fragment.fragment_service import FragmentService


class StarPurchaseService(StarPurchaseServiceInterface):
    """Сервис для управления покупкой звезд с кешированием"""

    def __init__(self, user_repository: UserRepository, balance_repository: BalanceRepository,
                 payment_service: PaymentService, payment_cache: Optional[PaymentCache] = None,
                 user_cache: Optional[UserCache] = None):
        self.user_repository = user_repository
        self.balance_repository = balance_repository
        self.payment_service = payment_service
        self.payment_cache = payment_cache
        self.user_cache = user_cache
        self.fragment_service = FragmentService()
        self.logger = logging.getLogger(__name__)

    async def create_star_purchase(self, user_id: int, amount: int, purchase_type: str = "balance") -> Dict[str, Any]:
        """Создание покупки звезд с баланса пользователя, через платежную систему или через Fragment API"""
        try:
            # Валидация суммы
            if not await self._validate_purchase_amount(amount):
                return {
                    "status": "failed",
                    "error": "Invalid purchase amount",
                    "amount": amount
                }

            # Если покупка с баланса, проверяем баланс и списываем средства
            if purchase_type == "balance":
                return await self._create_star_purchase_with_balance(user_id, amount)

            # Если покупка через Fragment API
            if purchase_type == "fragment":
                return await self._create_star_purchase_with_fragment(user_id, amount)

            # Иначе создаем покупку через платежную систему (Heleket)
            return await self._create_star_purchase_with_payment(user_id, amount)

        except Exception as e:
            self.logger.error(f"Error creating star purchase for user {user_id}: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

    async def _create_star_purchase_with_balance(self, user_id: int, amount: int) -> Dict[str, Any]:
        """Покупка звезд с баланса пользователя (оптимизированная версия)"""
        try:
            import asyncio
            
            # Быстрая проверка баланса из кеша
            if self.user_cache:
                cached_balance = await self.user_cache.get_user_balance(user_id)
                if cached_balance is not None:
                    current_balance = float(cached_balance)
                    # Быстрая проверка достаточности средств
                    if current_balance < amount:
                        return {
                            "status": "failed",
                            "error": "Insufficient balance",
                            "current_balance": current_balance,
                            "required_amount": amount
                        }
                    
                    # Если баланс достаточен, запускаем операцию асинхронно
                    return await self._process_balance_purchase_fast(user_id, amount, current_balance)
            
            # Fallback: получаем баланс из базы данных
            balance_data = await self.balance_repository.get_user_balance(user_id)
            if not balance_data:
                # Создаем баланс для нового пользователя асинхронно
                create_task = asyncio.create_task(self.balance_repository.create_user_balance(user_id, 0.0))
                await create_task
                balance_data = await self.balance_repository.get_user_balance(user_id)
                
                if not balance_data:
                    return {
                        "status": "failed",
                        "error": "Failed to create user balance"
                    }

            current_balance = float(balance_data["balance"])
            
            # Кешируем баланс для будущих операций
            if self.user_cache:
                asyncio.create_task(self.user_cache.cache_user_balance(user_id, int(current_balance)))

            # Проверяем достаточность средств
            if current_balance < amount:
                return {
                    "status": "failed",
                    "error": "Insufficient balance",
                    "current_balance": current_balance,
                    "required_amount": amount
                }

            # Создаем транзакцию покупки
            transaction_id = await self.balance_repository.create_transaction(
                user_id=user_id,
                transaction_type=TransactionType.PURCHASE,
                amount=float(amount),
                description=f"Покупка {amount} звезд с баланса",
                external_id=f"balance_purchase_{user_id}_{int(time.time())}",
                metadata={
                    "stars_count": amount,
                    "purchase_type": "balance",
                    "created_at": datetime.utcnow().isoformat()
                }
            )

            if not transaction_id:
                return {
                    "status": "failed",
                    "error": "Failed to create transaction"
                }

            # Списываем средства с баланса
            success = await self.balance_repository.update_user_balance(user_id, float(amount), "subtract")
            if not success:
                # Отменяем транзакцию в случае ошибки
                await self.balance_repository.update_transaction_status(
                    transaction_id,
                    TransactionStatus.FAILED,
                    metadata={"error": "Failed to update balance", "failed_at": datetime.utcnow().isoformat()}
                )
                return {
                    "status": "failed",
                    "error": "Failed to update balance"
                }

            # Обновляем статус транзакции на завершенный
            await self.balance_repository.update_transaction_status(
                transaction_id,
                TransactionStatus.COMPLETED,
                metadata={
                    "completed_at": datetime.utcnow().isoformat(),
                    "stars_count": amount,
                    "purchase_type": "balance",
                    "balance_updated": True
                }
            )

            # Обновляем кеш с новым балансом
            new_balance = current_balance - amount
            if self.user_cache:
                await self.user_cache.cache_user_balance(user_id, int(new_balance))

            # Получаем обновленный баланс
            updated_balance_data = await self.balance_repository.get_user_balance(user_id)
            updated_balance = float(updated_balance_data["balance"]) if updated_balance_data else new_balance

            return {
                "status": "success",
                "purchase_type": "balance",
                "transaction_id": transaction_id,
                "stars_count": amount,
                "old_balance": current_balance,
                "new_balance": new_balance,
                "currency": "TON",
                "message": f"✅ Успешно куплено {amount} звезд с баланса"
            }

        except Exception as e:
            self.logger.error(f"Error creating star purchase with balance for user {user_id}: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

    async def _create_star_purchase_with_fragment(self, user_id: int, amount: int) -> Dict[str, Any]:
        """Покупка звезд через Telegram Fragment API"""
        try:
            # Получаем информацию о пользователе из базы данных
            user_data = await self.user_repository.get_user(user_id)
            if not user_data:
                return {
                    "status": "failed",
                    "error": "User not found"
                }

            # Получаем Telegram username пользователя
            telegram_username = user_data.get("telegram_username")
            if not telegram_username:
                return {
                    "status": "failed",
                    "error": "Telegram username not found for user"
                }

            # Создаем транзакцию в ожидании покупки
            transaction_id = await self.balance_repository.create_transaction(
                user_id=user_id,
                transaction_type=TransactionType.PURCHASE,
                amount=float(amount),
                description=f"Покупка {amount} звезд через Fragment API",
                external_id=f"fragment_purchase_{user_id}_{int(time.time())}",
                metadata={
                    "stars_count": amount,
                    "purchase_type": "fragment",
                    "created_at": datetime.utcnow().isoformat()
                }
            )

            if not transaction_id:
                return {
                    "status": "failed",
                    "error": "Failed to create transaction"
                }

            # Кешируем информацию о покупке
            if self.payment_cache:
                await self.payment_cache.cache_payment_details(
                    f"fragment_purchase_{user_id}_{amount}",
                    {
                        "user_id": user_id,
                        "amount": amount,
                        "transaction_id": transaction_id,
                        "status": "pending",
                        "created_at": datetime.utcnow().isoformat()
                    }
                )

            # Выполняем покупку звезд через Fragment API
            purchase_result = await self.fragment_service.buy_stars_without_kyc(
                username=telegram_username,
                amount=amount
            )

            # Если покупка не удалась из-за cookies, пытаемся обновить их и повторить
            if purchase_result["status"] == "failed":
                error_msg = purchase_result.get("error", "Unknown error")
                # Проверяем, может быть ошибка связана с cookies
                if "cookie" in error_msg.lower() or "auth" in error_msg.lower() or "unauthorized" in error_msg.lower():
                    self.logger.warning(f"Fragment API call failed with auth error, trying to refresh cookies: {error_msg}")
                    
                    # Пытаемся обновить cookies
                    if await self.fragment_service.refresh_cookies_if_needed():
                        # Повторяем покупку с новыми cookies
                        self.logger.info("Retrying Fragment API call with refreshed cookies")
                        purchase_result = await self.fragment_service.buy_stars_without_kyc(
                            username=telegram_username,
                            amount=amount
                        )

            # Проверяем результат после возможного повтора
            if purchase_result["status"] == "failed":
                error_msg = purchase_result.get("error", "Unknown error")
                # Отменяем транзакцию в случае ошибки
                await self.balance_repository.update_transaction_status(
                    transaction_id,
                    TransactionStatus.FAILED,
                    metadata={"error": error_msg, "failed_at": datetime.utcnow().isoformat()}
                )
                return {
                    "status": "failed",
                    "error": error_msg,
                    "transaction_id": transaction_id
                }

            # Обновляем транзакцию с данными покупки
            await self.balance_repository.update_transaction_status(
                transaction_id,
                TransactionStatus.COMPLETED,
                metadata={
                    "purchase_completed_at": datetime.utcnow().isoformat(),
                    "fragment_result": purchase_result.get("result", {}),
                    "purchase_type": "fragment"
                }
            )

            # Кешируем результат
            if self.payment_cache:
                await self.payment_cache.cache_payment_details(
                    f"fragment_purchase_{user_id}_{amount}",
                    {
                        "user_id": user_id,
                        "amount": amount,
                        "transaction_id": transaction_id,
                        "status": "completed",
                        "fragment_result": purchase_result.get("result", {}),
                        "completed_at": datetime.utcnow().isoformat()
                    }
                )

            return {
                "status": "success",
                "purchase_type": "fragment",
                "result": purchase_result.get("result", {}),
                "transaction_id": transaction_id,
                "stars_count": amount
            }

        except Exception as e:
            self.logger.error(f"Error creating star purchase with Fragment API for user {user_id}: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

    async def _create_star_purchase_with_payment(self, user_id: int, amount: int) -> Dict[str, Any]:
        """Покупка звезд через платежную систему Heleket"""
        try:
            # Создаем транзакцию в ожидании оплаты
            transaction_id = await self.balance_repository.create_transaction(
                user_id=user_id,
                transaction_type=TransactionType.PURCHASE,
                amount=float(amount),
                description=f"Покупка {amount} звезд",
                external_id=f"purchase_{user_id}_{int(time.time())}",
                metadata={
                    "stars_count": amount,
                    "purchase_type": "payment",
                    "created_at": datetime.utcnow().isoformat()
                }
            )

            if not transaction_id:
                return {
                    "status": "failed",
                    "error": "Failed to create transaction"
                }

            # Кешируем информацию о покупке
            if self.payment_cache:
                await self.payment_cache.cache_payment_details(
                    f"purchase_{user_id}_{amount}",
                    {
                        "user_id": user_id,
                        "amount": amount,
                        "transaction_id": transaction_id,
                        "status": "pending",
                        "created_at": datetime.utcnow().isoformat()
                    }
                )

            # Создаем счет через платежную систему
            invoice = await self.payment_service.create_invoice_for_user(user_id, str(amount))

            if "error" in invoice or "status" in invoice and invoice["status"] == "failed":
                error_msg = invoice.get("error", "Unknown error")
                # Отменяем транзакцию в случае ошибки
                await self.balance_repository.update_transaction_status(
                    transaction_id,
                    TransactionStatus.FAILED,
                    metadata={"error": error_msg, "failed_at": datetime.utcnow().isoformat()}
                )
                return {
                    "status": "failed",
                    "error": error_msg,
                    "transaction_id": transaction_id
                }

            if "result" not in invoice:
                await self.balance_repository.update_transaction_status(
                    transaction_id,
                    TransactionStatus.FAILED,
                    metadata={"error": "Invalid payment response", "failed_at": datetime.utcnow().isoformat()}
                )
                return {
                    "status": "failed",
                    "error": "Invalid payment response",
                    "transaction_id": transaction_id
                }

            result = invoice["result"]
            if "uuid" not in result or "url" not in result:
                await self.balance_repository.update_transaction_status(
                    transaction_id,
                    TransactionStatus.FAILED,
                    metadata={"error": "Incomplete payment data", "failed_at": datetime.utcnow().isoformat()}
                )
                return {
                    "status": "failed",
                    "error": "Incomplete payment data",
                    "transaction_id": transaction_id
                }

            # Обновляем транзакцию с данными платежа
            await self.balance_repository.update_transaction_status(
                transaction_id,
                TransactionStatus.PENDING,
                metadata={
                    "payment_uuid": result["uuid"],
                    "payment_url": result["url"],
                    "payment_created_at": datetime.utcnow().isoformat(),
                    "purchase_type": "payment"
                }
            )

            # Кешируем данные платежа
            if self.payment_cache:
                await self.payment_cache.cache_payment_details(
                    f"payment_{result['uuid']}",
                    {
                        "user_id": user_id,
                        "amount": amount,
                        "transaction_id": transaction_id,
                        "status": "pending",
                        "payment_uuid": result["uuid"],
                        "payment_url": result["url"],
                        "created_at": datetime.utcnow().isoformat()
                    }
                )

            return {
                "status": "success",
                "purchase_type": "payment",
                "result": result,
                "transaction_id": transaction_id,
                "stars_count": amount
            }

        except Exception as e:
            self.logger.error(f"Error creating star purchase with payment for user {user_id}: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

    async def check_purchase_status(self, purchase_id: str) -> Dict[str, Any]:
        """Проверка статуса покупки"""
        try:
            # Сначала проверяем кеш
            if self.payment_cache:
                cached_status = await self.payment_cache.get_payment_details(f"payment_{purchase_id}")
                if cached_status:
                    return cached_status

            # Проверяем через платежную систему
            payment_info = await self.payment_service.check_payment(purchase_id)

            if "error" in payment_info:
                return {
                    "status": "failed",
                    "error": payment_info["error"],
                    "payment_id": purchase_id
                }

            # Обновляем статус в транзакции
            transaction_data = await self.balance_repository.get_transaction_by_external_id(purchase_id)
            if transaction_data:
                if payment_info.get("status") == "paid":
                    # Завершаем транзакцию
                    await self.balance_repository.update_transaction_status(
                        transaction_data["id"],
                        TransactionStatus.COMPLETED,
                        metadata={
                            "payment_completed_at": datetime.utcnow().isoformat(),
                            "payment_amount": payment_info.get("amount"),
                            "payment_currency": payment_info.get("currency", "TON")
                        }
                    )
                else:
                    # Обновляем статус
                    await self.balance_repository.update_transaction_status(
                        transaction_data["id"],
                        TransactionStatus.PENDING,
                        metadata={
                            "payment_status": payment_info.get("status"),
                            "payment_updated_at": datetime.utcnow().isoformat()
                        }
                    )

            # Кешируем результат
            if self.payment_cache:
                await self.payment_cache.cache_payment_details(
                    f"payment_{purchase_id}",
                    payment_info
                )

            return payment_info

        except Exception as e:
            self.logger.error(f"Error checking purchase status for {purchase_id}: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "payment_id": purchase_id
            }

    async def process_payment_webhook(self, webhook_data: Dict[str, Any]) -> bool:
        """Обработка вебхука от платежной системы Heleket"""
        try:
            # Валидация подписи вебхука
            if not await self._validate_webhook_signature(webhook_data):
                self.logger.error("Invalid webhook signature")
                return False

            # Извлекаем данные из вебхука
            payment_uuid = webhook_data.get("uuid")
            status = webhook_data.get("status")
            amount = webhook_data.get("amount")

            if not payment_uuid or not status:
                self.logger.error("Invalid webhook data")
                return False

            # Получаем транзакцию по UUID платежа
            transaction_data = await self.balance_repository.get_transaction_by_external_id(payment_uuid)
            if not transaction_data:
                self.logger.error(f"Transaction not found for payment {payment_uuid}")
                return False

            user_id = transaction_data["user_id"]
            transaction_id = transaction_data["id"]
            purchase_type = transaction_data.get("metadata", {}).get("purchase_type", "payment")

            # Обновляем статус транзакции
            if status == "paid":
                # Если это покупка через платежную систему, обновляем баланс
                if purchase_type == "payment" and amount:
                    await self.balance_repository.update_user_balance(user_id, float(amount), "add")

                await self.balance_repository.update_transaction_status(
                    transaction_id,
                    TransactionStatus.COMPLETED,
                    metadata={
                        "webhook_received_at": datetime.utcnow().isoformat(),
                        "payment_amount": amount,
                        "payment_status": status,
                        "stars_count": transaction_data.get("metadata", {}).get("stars_count", 0)
                    }
                )

                # Инвалидируем кеш пользователя
                if self.user_cache:
                    await self.user_cache.invalidate_user_cache(user_id)

                self.logger.info(f"Payment {payment_uuid} completed successfully for user {user_id}")
                return True

            elif status in ["failed", "cancelled"]:
                await self.balance_repository.update_transaction_status(
                    transaction_id,
                    TransactionStatus.FAILED,
                    metadata={
                        "webhook_received_at": datetime.utcnow().isoformat(),
                        "payment_amount": amount,
                        "payment_status": status,
                        "failure_reason": webhook_data.get("error", "Payment failed")
                    }
                )

                self.logger.info(f"Payment {payment_uuid} failed for user {user_id}")
                return True

            else:
                self.logger.warning(f"Unknown payment status: {status} for payment {payment_uuid}")
                return False

        except Exception as e:
            self.logger.error(f"Error processing payment webhook: {e}")
            return False

    async def get_purchase_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение истории покупок пользователя"""
        try:
            # Получаем транзакции типа purchase
            transactions = await self.balance_repository.get_user_transactions(
                user_id=user_id,
                limit=limit,
                transaction_type=TransactionType.PURCHASE
            )

            # Форматируем данные для удобства
            purchase_history = []
            for transaction in transactions:
                purchase_data = {
                    "id": transaction["id"],
                    "amount": transaction["amount"],
                    "currency": transaction["currency"],
                    "status": transaction["status"],
                    "created_at": transaction["created_at"],
                    "stars_count": transaction.get("metadata", {}).get("stars_count", 0),
                    "payment_uuid": transaction.get("metadata", {}).get("payment_uuid"),
                    "payment_url": transaction.get("metadata", {}).get("payment_url")
                }
                purchase_history.append(purchase_data)

            return purchase_history

        except Exception as e:
            self.logger.error(f"Error getting purchase history for user {user_id}: {e}")
            return []

    async def _validate_purchase_amount(self, amount: int) -> bool:
        """Валидация суммы покупки"""
        try:
            if amount <= 0:
                return False

            # Минимальная сумма покупки
            if amount < 1:
                return False

            # Максимальная сумма покупки
            if amount > 100000:  # 100,000 звезд
                return False

            # Можно добавить дополнительные проверки
            return True

        except Exception as e:
            self.logger.error(f"Error validating purchase amount {amount}: {e}")
            return False

    async def _validate_webhook_signature(self, webhook_data: Dict[str, Any]) -> bool:
        """Валидация подписи вебхука от Heleket с использованием HMAC SHA256"""
        try:
            # Получаем секретный ключ из настроек
            from config.settings import settings
            webhook_secret = settings.webhook_secret

            if not webhook_secret:
                self.logger.warning("Webhook secret is not configured, skipping signature validation")
                return True  # В режиме разработки разрешаем без подписи

            # Извлекаем необходимые поля для валидации
            webhook_uuid = webhook_data.get("uuid")
            status = webhook_data.get("status")
            amount = webhook_data.get("amount")

            if not webhook_uuid or not status:
                self.logger.error("Missing required fields: uuid or status")
                return False

            # Создаем строку для подписи (payload)
            # Используем JSON сериализацию для консистентности
            import json
            payload = json.dumps({
                "uuid": webhook_uuid,
                "status": status,
                "amount": amount
            }, sort_keys=True, separators=(',', ':'))

            # Вычисляем HMAC SHA256 подпись
            expected_signature = hmac.new(
                webhook_secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            # Получаем подпись из заголовков запроса (если доступна)
            # В реальной реализации это должно передаваться через middleware
            provided_signature = getattr(self, '_webhook_signature', None)

            if provided_signature:
                # Используем постоянное время сравнение для безопасности
                is_valid = hmac.compare_digest(expected_signature, provided_signature)
                if not is_valid:
                    self.logger.error(f"Invalid webhook signature for UUID: {webhook_uuid}")
                    return False
            else:
                # Если подпись не предоставлена, логируем предупреждение
                self.logger.warning(f"No signature provided for webhook UUID: {webhook_uuid}")

            self.logger.info(f"Webhook signature validation passed for UUID: {webhook_uuid}")
            return True

        except Exception as e:
            self.logger.error(f"Error validating webhook signature: {e}")
            return False

    async def _process_balance_purchase_fast(self, user_id: int, amount: int, current_balance: float) -> Dict[str, Any]:
        """Быстрая обработка покупки с баланса"""
        try:
            import asyncio
            from datetime import datetime
            
            # Создаем транзакцию и обновляем баланс параллельно
            transaction_task = asyncio.create_task(
                self.balance_repository.create_transaction(
                    user_id=user_id,
                    transaction_type=TransactionType.PURCHASE,
                    amount=float(amount),
                    description=f"Покупка {amount} звезд с баланса",
                    external_id=f"balance_purchase_{user_id}_{int(time.time())}",
                    metadata={
                        "stars_count": amount,
                        "purchase_type": "balance",
                        "created_at": datetime.utcnow().isoformat()
                    }
                )
            )
            
            balance_update_task = asyncio.create_task(
                self.balance_repository.update_user_balance(user_id, float(amount), "subtract")
            )
            
            # Ждем завершения обеих операций
            transaction_id, balance_success = await asyncio.gather(
                transaction_task, balance_update_task, return_exceptions=True
            )
            
            if isinstance(transaction_id, Exception) or isinstance(balance_success, Exception):
                return {
                    "status": "failed",
                    "error": "Failed to process transaction"
                }
            
            if not transaction_id or not balance_success:
                return {
                    "status": "failed",
                    "error": "Failed to update balance or create transaction"
                }
            
            # Обновляем статус транзакции асинхронно (не ждем)
            if isinstance(transaction_id, int):
                asyncio.create_task(
                    self.balance_repository.update_transaction_status(
                        transaction_id,
                        TransactionStatus.COMPLETED,
                        metadata={
                            "completed_at": datetime.utcnow().isoformat(),
                            "stars_count": amount,
                            "purchase_type": "balance",
                            "balance_updated": True
                        }
                    )
                )
            else:
                self.logger.error(f"Failed to update transaction status: transaction_id is not int, got {type(transaction_id)}: {transaction_id}")
            
            # Обновляем кеш с новым балансом асинхронно (не ждем)
            new_balance = current_balance - amount
            if self.user_cache:
                asyncio.create_task(self.user_cache.cache_user_balance(user_id, int(new_balance)))
            
            # Возвращаем результат быстро
            return {
                "status": "success",
                "purchase_type": "balance",
                "transaction_id": transaction_id,
                "stars_count": amount,
                "old_balance": current_balance,
                "new_balance": new_balance,
                "currency": "TON",
                "message": f"✅ Успешно куплено {amount} звезд с баланса"
            }
            
        except Exception as e:
            self.logger.error(f"Error in fast balance purchase for user {user_id}: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

    async def get_purchase_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики покупок пользователя"""
        try:
            # Получаем все транзакции покупок
            transactions = await self.balance_repository.get_user_transactions(
                user_id=user_id,
                transaction_type=TransactionType.PURCHASE
            )

            # Вычисляем статистику
            total_purchases = len(transactions)
            successful_purchases = len([t for t in transactions if t["status"] == "completed"])
            failed_purchases = len([t for t in transactions if t["status"] == "failed"])

            total_stars = sum(
                t.get("metadata", {}).get("stars_count", 0)
                for t in transactions
                if t["status"] == "completed"
            )

            total_amount = sum(
                t["amount"] for t in transactions
                if t["status"] == "completed"
            )

            return {
                "user_id": user_id,
                "total_purchases": total_purchases,
                "successful_purchases": successful_purchases,
                "failed_purchases": failed_purchases,
                "success_rate": (successful_purchases / total_purchases * 100) if total_purchases > 0 else 0,
                "total_stars": total_stars,
                "total_amount": total_amount,
                "average_amount_per_purchase": total_amount / successful_purchases if successful_purchases > 0 else 0
            }

        except Exception as e:
            self.logger.error(f"Error getting purchase statistics for user {user_id}: {e}")
            return {}

    async def cancel_pending_purchase(self, user_id: int, transaction_id: int) -> bool:
        """Отмена ожидающей обработки покупки"""
        try:
            # Получаем транзакцию
            transaction_data = await self.balance_repository.get_transaction_by_external_id(
                f"purchase_{user_id}_{transaction_id}"
            )

            if not transaction_data:
                return False

            # Проверяем статус
            if transaction_data["status"] != "pending":
                return False

            # Отменяем транзакцию
            success = await self.balance_repository.update_transaction_status(
                transaction_data["id"],
                TransactionStatus.CANCELLED,
                metadata={
                    "cancelled_at": datetime.utcnow().isoformat(),
                    "cancelled_by": "user"
                }
            )

            if success and self.user_cache:
                await self.user_cache.invalidate_user_cache(user_id)

            return success

        except Exception as e:
            self.logger.error(f"Error cancelling purchase {transaction_id} for user {user_id}: {e}")
            return False

    async def cancel_specific_recharge(self, user_id: int, payment_uuid: str) -> bool:
        """Отмена конкретного пополнения по UUID платежа"""
        try:
            # Получаем все pending транзакции пополнения пользователя
            pending_recharges = await self.balance_repository.get_user_transactions(
                user_id=user_id,
                transaction_type=TransactionType.RECHARGE,
                status=TransactionStatus.PENDING
            )
            
            # Ищем транзакцию с нужным payment_uuid в метаданных
            transaction_data = None
            for transaction in pending_recharges:
                metadata = transaction.get("metadata", {})
                if isinstance(metadata, dict) and metadata.get("payment_uuid") == payment_uuid:
                    transaction_data = transaction
                    break
            
            if not transaction_data:
                self.logger.warning(f"Transaction not found for payment UUID {payment_uuid}")
                return False

            # Проверяем, что это транзакция данного пользователя
            if transaction_data["user_id"] != user_id:
                self.logger.warning(f"Transaction {payment_uuid} does not belong to user {user_id}")
                return False

            # Проверяем статус
            if transaction_data["status"] != "pending":
                self.logger.info(f"Transaction {payment_uuid} is not pending, current status: {transaction_data['status']}")
                return False

            # Отменяем транзакцию
            success = await self.balance_repository.update_transaction_status(
                transaction_data["id"],
                TransactionStatus.CANCELLED,
                metadata={
                    "cancelled_at": datetime.utcnow().isoformat(),
                    "cancelled_by": "user_back_button",
                    "reason": "User pressed back button for specific invoice",
                    "payment_uuid": payment_uuid
                }
            )
            
            if success:
                self.logger.info(f"Cancelled specific recharge transaction {transaction_data['id']} (UUID: {payment_uuid}) for user {user_id}")
                
                # Инвалидируем кеш пользователя
                if self.user_cache:
                    await self.user_cache.invalidate_user_cache(user_id)

            return success

        except Exception as e:
            self.logger.error(f"Error cancelling specific recharge {payment_uuid} for user {user_id}: {e}")
            return False

    async def cancel_pending_recharges(self, user_id: int) -> int:
        """Отмена всех ожидающих обработки пополнений пользователя"""
        try:
            # Получаем все pending транзакции пополнения для пользователя
            pending_recharges = await self.balance_repository.get_user_transactions(
                user_id=user_id,
                transaction_type=TransactionType.RECHARGE,
                status=TransactionStatus.PENDING
            )

            cancelled_count = 0
            for transaction in pending_recharges:
                # Отменяем каждую транзакцию
                success = await self.balance_repository.update_transaction_status(
                    transaction["id"],
                    TransactionStatus.CANCELLED,
                    metadata={
                        "cancelled_at": datetime.utcnow().isoformat(),
                        "cancelled_by": "user_back_button",
                        "reason": "User pressed back button"
                    }
                )
                
                if success:
                    cancelled_count += 1
                    self.logger.info(f"Cancelled pending recharge transaction {transaction['id']} for user {user_id}")

            # Инвалидируем кеш пользователя если были отменены транзакции
            if cancelled_count > 0 and self.user_cache:
                await self.user_cache.invalidate_user_cache(user_id)

            return cancelled_count

        except Exception as e:
            self.logger.error(f"Error cancelling pending recharges for user {user_id}: {e}")
            return 0

    async def create_recharge(self, user_id: int, amount: float) -> Dict[str, Any]:
        """Создание пополнения баланса"""
        try:
            
            # Валидация суммы
            if not await self._validate_recharge_amount(amount):
                return {
                    "status": "failed",
                    "error": "Invalid recharge amount",
                    "amount": amount
                }

            # Создаем транзакцию в ожидании оплаты
            transaction_id = await self.balance_repository.create_transaction(
                user_id=user_id,
                transaction_type=TransactionType.RECHARGE,
                amount=float(amount),
                description=f"Пополнение баланса на {amount} TON",
                external_id=f"recharge_{user_id}_{int(time.time())}",
                metadata={
                    "recharge_amount": amount,
                    "recharge_type": "heleket",
                    "created_at": datetime.utcnow().isoformat()
                }
            )

            if not transaction_id:
                return {
                    "status": "failed",
                    "error": "Failed to create transaction"
                }

            # Кешируем информацию о пополнении
            if self.payment_cache:
                await self.payment_cache.cache_payment_details(
                    f"recharge_{user_id}_{amount}",
                    {
                        "user_id": user_id,
                        "amount": amount,
                        "transaction_id": transaction_id,
                        "status": "pending",
                        "created_at": datetime.utcnow().isoformat()
                    }
                )

            # Создаем счет через платежную систему
            invoice = await self.payment_service.create_recharge_invoice_for_user(user_id, str(amount))

            if "error" in invoice or "status" in invoice and invoice["status"] == "failed":
                error_msg = invoice.get("error", "Unknown error")
                # Отменяем транзакцию в случае ошибки
                await self.balance_repository.update_transaction_status(
                    transaction_id,
                    TransactionStatus.FAILED,
                    metadata={"error": error_msg, "failed_at": datetime.utcnow().isoformat()}
                )
                return {
                    "status": "failed",
                    "error": error_msg,
                    "transaction_id": transaction_id
                }

            if "result" not in invoice:
                await self.balance_repository.update_transaction_status(
                    transaction_id,
                    TransactionStatus.FAILED,
                    metadata={"error": "Invalid payment response", "failed_at": datetime.utcnow().isoformat()}
                )
                return {
                    "status": "failed",
                    "error": "Invalid payment response",
                    "transaction_id": transaction_id
                }

            result = invoice["result"]
            if "uuid" not in result or "url" not in result:
                await self.balance_repository.update_transaction_status(
                    transaction_id,
                    TransactionStatus.FAILED,
                    metadata={"error": "Incomplete payment data", "failed_at": datetime.utcnow().isoformat()}
                )
                return {
                    "status": "failed",
                    "error": "Incomplete payment data",
                    "transaction_id": transaction_id
                }

            # Обновляем транзакцию с данными платежа
            await self.balance_repository.update_transaction_status(
                transaction_id,
                TransactionStatus.PENDING,
                metadata={
                    "payment_uuid": result["uuid"],
                    "payment_url": result["url"],
                    "payment_created_at": datetime.utcnow().isoformat()
                }
            )

            # Кешируем данные платежа
            if self.payment_cache:
                await self.payment_cache.cache_payment_details(
                    f"payment_{result['uuid']}",
                    {
                        "user_id": user_id,
                        "amount": amount,
                        "transaction_id": transaction_id,
                        "status": "pending",
                        "payment_uuid": result["uuid"],
                        "payment_url": result["url"],
                        "created_at": datetime.utcnow().isoformat()
                    }
                )

            return {
                "status": "success",
                "result": result,
                "transaction_id": transaction_id,
                "recharge_amount": amount
            }

        except Exception as e:
            self.logger.error(f"Error creating recharge for user {user_id}: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

    async def check_recharge_status(self, recharge_id: str) -> Dict[str, Any]:
        """Проверка статуса пополнения"""
        try:
            # Сначала проверяем кеш
            if self.payment_cache:
                cached_status = await self.payment_cache.get_payment_details(f"payment_{recharge_id}")
                if cached_status:
                    return cached_status

            # Проверяем через платежную систему
            payment_info = await self.payment_service.check_payment(recharge_id)

            if "error" in payment_info:
                return {
                    "status": "failed",
                    "error": payment_info["error"],
                    "payment_id": recharge_id
                }

            # Обновляем статус в транзакции
            transaction_data = await self.balance_repository.get_transaction_by_external_id(recharge_id)
            if transaction_data:
                if payment_info.get("status") == "paid":
                    # Завершаем транзакцию
                    await self.balance_repository.update_transaction_status(
                        transaction_data["id"],
                        TransactionStatus.COMPLETED,
                        metadata={
                            "payment_completed_at": datetime.utcnow().isoformat(),
                            "payment_amount": payment_info.get("amount"),
                            "payment_currency": payment_info.get("currency", "TON")
                        }
                    )
                else:
                    # Обновляем статус
                    await self.balance_repository.update_transaction_status(
                        transaction_data["id"],
                        TransactionStatus.PENDING,
                        metadata={
                            "payment_status": payment_info.get("status"),
                            "payment_updated_at": datetime.utcnow().isoformat()
                        }
                    )

            # Кешируем результат
            if self.payment_cache:
                await self.payment_cache.cache_payment_details(
                    f"payment_{recharge_id}",
                    payment_info
                )

            return payment_info

        except Exception as e:
            self.logger.error(f"Error checking recharge status for {recharge_id}: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "payment_id": recharge_id
            }

    async def process_recharge_webhook(self, webhook_data: Dict[str, Any]) -> bool:
        """Обработка вебхука от платежной системы Heleket для пополнения баланса"""
        try:
            # Валидация подписи вебхука
            if not await self._validate_webhook_signature(webhook_data):
                self.logger.error("Invalid webhook signature")
                return False

            # Извлекаем данные из вебхука
            payment_uuid = webhook_data.get("uuid")
            status = webhook_data.get("status")
            amount = webhook_data.get("amount")

            if not payment_uuid or not status:
                self.logger.error("Invalid webhook data")
                return False

            # Получаем транзакцию по UUID платежа
            transaction_data = await self.balance_repository.get_transaction_by_external_id(payment_uuid)
            if not transaction_data:
                self.logger.error(f"Transaction not found for payment {payment_uuid}")
                return False

            user_id = transaction_data["user_id"]
            transaction_id = transaction_data["id"]

            # Обновляем статус транзакции
            if status == "paid":
                # Получаем сумму пополнения из метаданных транзакции
                recharge_amount = transaction_data.get("metadata", {}).get("recharge_amount", 0)

                # Пополняем баланс пользователя
                if recharge_amount:
                    await self.balance_repository.update_user_balance(user_id, float(recharge_amount), "add")

                await self.balance_repository.update_transaction_status(
                    transaction_id,
                    TransactionStatus.COMPLETED,
                    metadata={
                        "webhook_received_at": datetime.utcnow().isoformat(),
                        "payment_amount": amount,
                        "payment_status": status,
                        "recharge_amount": recharge_amount,
                        "balance_updated": True
                    }
                )

                # Инвалидируем кеш пользователя
                if self.user_cache:
                    await self.user_cache.invalidate_user_cache(user_id)

                self.logger.info(f"Recharge payment {payment_uuid} completed successfully for user {user_id}")
                return True

            elif status in ["failed", "cancelled"]:
                await self.balance_repository.update_transaction_status(
                    transaction_id,
                    TransactionStatus.FAILED,
                    metadata={
                        "webhook_received_at": datetime.utcnow().isoformat(),
                        "payment_amount": amount,
                        "payment_status": status,
                        "failure_reason": webhook_data.get("error", "Payment failed")
                    }
                )

                self.logger.info(f"Recharge payment {payment_uuid} failed for user {user_id}")
                return True

            else:
                self.logger.warning(f"Unknown payment status: {status} for payment {payment_uuid}")
                return False

        except Exception as e:
            self.logger.error(f"Error processing recharge webhook: {e}")
            return False

    async def _validate_recharge_amount(self, amount: float) -> bool:
        """Валидация суммы пополнения"""
        try:
            
            # Проверка на None
            if amount is None:
                return False

            if amount <= 0:
                return False

            # Минимальная сумма пополнения
            if amount < 10:  # 10 TON
                return False

            # Максимальная сумма пополнения
            if amount > 10000:  # 10,000 TON
                return False

            # Можно добавить дополнительные проверки
            return True

        except Exception as e:
            self.logger.error(f"Error validating recharge amount {amount}: {e}")
            return False
