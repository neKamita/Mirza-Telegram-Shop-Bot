"""
Сервис для работы с платежной системой с интеграцией кеширования
"""
import json
import hashlib
import base64
import aiohttp
import time
from typing import Dict, Any, Optional
from core.interfaces import PaymentInterface
from services.payment_cache import PaymentCache


class PaymentService(PaymentInterface):
    """Сервис для управления платежами с кешированием"""

    def __init__(self, merchant_uuid: str, api_key: str, payment_cache: Optional[PaymentCache] = None):
        self.merchant_uuid = merchant_uuid
        self.api_key = api_key
        self.payment_cache = payment_cache
        self.base_url = "https://api.heleket.com/v1"

    def _generate_headers(self, data: str) -> Dict[str, str]:
        """Генерация заголовков для запросов"""
        signature = hashlib.md5(
            base64.b64encode(data.encode("ascii")) +
            self.api_key.encode("ascii")
        ).hexdigest()
        return {
            "merchant": self.merchant_uuid,
            "sign": signature,
            "Content-Type": "application/json"
        }

    async def create_invoice(self, amount: str, currency: str, order_id: str) -> Dict[str, Any]:
        """Создание счета на оплату с кешированием"""
        cache_key = f"invoice:{order_id}"

        # Проверяем кеш
        if self.payment_cache:
            cached_invoice = await self.payment_cache.get_payment_details(cache_key)
            if cached_invoice:
                return cached_invoice

        payload = {
            "amount": amount,
            "currency": currency,
            "order_id": order_id
        }

        json_data = json.dumps(payload)
        headers = self._generate_headers(json_data)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/payment",
                    headers=headers,
                    data=json_data
                ) as response:
                    result = await response.json()

                    # Кешируем результат
                    if self.payment_cache and "result" in result:
                        await self.payment_cache.cache_payment_details(
                            cache_key,
                            result
                        )

                    return result
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    async def check_payment(self, invoice_uuid: str) -> Dict[str, Any]:
        """Проверка статуса оплаты с кешированием"""
        cache_key = f"payment_status:{invoice_uuid}"

        # Проверяем кеш
        if self.payment_cache:
            cached_status = await self.payment_cache.get_payment_details(cache_key)
            if cached_status:
                return cached_status

        payload = {"uuid": invoice_uuid}
        json_data = json.dumps(payload)
        headers = self._generate_headers(json_data)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/payment/info",
                    headers=headers,
                    data=json_data
                ) as response:
                    result = await response.json()

                    # Кешируем результат на короткое время для избежания частых запросов
                    if self.payment_cache:
                        await self.payment_cache.cache_payment_details(
                            cache_key,
                            result
                        )

                    return result
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    async def create_invoice_for_user(self, user_id: int, amount: str = "1") -> Dict[str, Any]:
        """Создание счета для конкретного пользователя с кешированием"""
        order_id = f"subscription-{user_id}-{int(time.time())}"

        # Кешируем информацию о заказе
        if self.payment_cache:
            await self.payment_cache.cache_payment_details(
                f"user_order:{user_id}:{order_id}",
                {
                    "user_id": user_id,
                    "amount": amount,
                    "currency": "TON",
                    "created_at": time.time()
                }
            )

        return await self.create_invoice(
            amount=amount,
            currency="TON",
            order_id=order_id
        )

    async def get_payment_history(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        """Получение истории платежей пользователя из кеша"""
        if not self.payment_cache:
            return {"error": "Payment cache not available", "status": "failed"}

        try:
            # Получаем все ключи платежей пользователя
            pattern = f"user_order:{user_id}:*"
            keys = await self.payment_cache.redis_client.keys(pattern)

            payments = []
            for key in keys[:limit]:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                payment_data = await self.payment_cache.get_payment_details(key_str)
                if payment_data:
                    payments.append(payment_data)

            return {
                "status": "success",
                "payments": payments,
                "total": len(payments)
            }
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    async def invalidate_payment_cache(self, invoice_uuid: str) -> bool:
        """Инвалидация кеша платежа"""
        if not self.payment_cache:
            return False

        try:
            cache_key = f"payment_status:{invoice_uuid}"
            await self.payment_cache.redis_client.delete(cache_key)
            return True
        except Exception:
            return False

    async def get_payment_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики платежей пользователя"""
        if not self.payment_cache:
            return {"error": "Payment cache not available", "status": "failed"}

        try:
            pattern = f"user_order:{user_id}:*"
            keys = await self.payment_cache.redis_client.keys(pattern)

            total_amount = 0
            payment_count = 0

            for key in keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                payment_data = await self.payment_cache.get_payment_details(key_str)
                if payment_data and "amount" in payment_data:
                    try:
                        total_amount += float(payment_data["amount"])
                        payment_count += 1
                    except (ValueError, TypeError):
                        continue

            return {
                "status": "success",
                "total_payments": payment_count,
                "total_amount": total_amount,
                "average_amount": total_amount / payment_count if payment_count > 0 else 0
            }
        except Exception as e:
            return {"error": str(e), "status": "failed"}
