"""
Сервис для работы с платежной системой с интеграцией кеширования
"""
import json
import hashlib
import hmac
import base64
import logging
import aiohttp
import time
from typing import Dict, Any, Optional
from core.interfaces import PaymentInterface
from services.cache.payment_cache import PaymentCache
from utils.message_formatter import MessageFormatter
from utils.message_templates import MessageTemplate


class PaymentService(PaymentInterface):
    """
    Сервис для управления платежами с кешированием
    Интеграция с Heleket API для обработки платежей в TON
    """

    def __init__(self, merchant_uuid: str, api_key: str, payment_cache: Optional[PaymentCache] = None, message_formatter: Optional[MessageFormatter] = None):
        self.merchant_uuid = merchant_uuid
        self.api_key = api_key
        self.payment_cache = payment_cache
        self.message_formatter = message_formatter
        self.base_url = "https://api.heleket.com/v1"
        self.logger = logging.getLogger(__name__)
        self.logger = logging.getLogger(__name__)

    def _generate_headers(self, data: str) -> Dict[str, str]:
        """Генерация заголовков для запросов"""
        signature = hashlib.md5(
            base64.b64encode(data.encode("ascii")) +
            self.api_key.encode("ascii")
        ).hexdigest()

        headers = {
            "merchant": self.merchant_uuid,
            "sign": signature,
            "Content-Type": "application/json"
        }

        self.logger.warning("Используется MD5 для совместимости с Heleket API")
        self.logger.debug(f"Generated headers: merchant={self.merchant_uuid[:8]}..., sign={signature[:8]}...")
        return headers

    async def create_invoice(self, amount: str, currency: str, order_id: str) -> Dict[str, Any]:
        """Создание счета на оплату с кешированием"""
        cache_key = f"invoice:{order_id}"
        self.logger.info(f"Creating invoice: amount={amount}, currency={currency}, order_id={order_id}")

        # Проверяем кеш
        if self.payment_cache:
            cached_invoice = await self.payment_cache.get_payment_details(cache_key)
            if cached_invoice:
                self.logger.info(f"Using cached invoice for {order_id}")
                return cached_invoice

        payload = {
            "amount": amount,
            "currency": currency,
            "order_id": order_id
        }

        json_data = json.dumps(payload)
        headers = self._generate_headers(json_data)

        self.logger.debug(f"Request payload: {json_data}")
        self.logger.debug(f"Request URL: {self.base_url}/payment")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/payment",
                    headers=headers,
                    data=json_data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    self.logger.info(f"Response status: {response.status}")
                    response_text = await response.text()
                    self.logger.debug(f"Response text: {response_text}")

                    try:
                        result = json.loads(response_text)
                        self.logger.info(f"Parsed JSON response: {result}")

                        # Кешируем результат
                        if self.payment_cache and "result" in result:
                            await self.payment_cache.cache_payment_details(
                                cache_key,
                                result
                            )
                            self.logger.info(f"Cached invoice for {order_id}")

                        return result
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Failed to parse JSON response: {e}")
                        return {"error": f"Invalid JSON response: {response_text}", "status": "failed"}

        except aiohttp.ClientError as e:
            self.logger.error(f"Network error during payment request: {e}")
            return {"error": f"Network error: {str(e)}", "status": "failed"}
        except Exception as e:
            self.logger.error(f"Unexpected error during payment request: {e}", exc_info=True)
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

    async def create_recharge_invoice(self, user_id: int, amount: str) -> Dict[str, Any]:
        """Создание счета на пополнение баланса с кешированием"""
        order_id = f"recharge-{user_id}-{int(time.time())}"

        # Кешируем информацию о пополнении
        if self.payment_cache:
            await self.payment_cache.cache_payment_details(
                f"recharge:{user_id}:{order_id}",
                {
                    "user_id": user_id,
                    "amount": amount,
                    "currency": "TON",
                    "type": "recharge",
                    "created_at": time.time()
                }
            )

        return await self.create_invoice(
            amount=amount,
            currency="TON",
            order_id=order_id
        )

    async def create_recharge_invoice_for_user(self, user_id: int, amount: str = "10") -> Dict[str, Any]:
        """Создание счета на пополнение баланса для конкретного пользователя с кешированием"""
        return await self.create_recharge_invoice(user_id, amount)

    async def get_recharge_history(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        """Получение истории пополнений пользователя из кеша"""
        if not self.payment_cache:
            return {"error": "Payment cache not available", "status": "failed"}

        try:
            # Получаем все ключи пополнений пользователя
            pattern = f"recharge:{user_id}:*"
            keys = await self.payment_cache.redis_client.execute_operation('keys', pattern)

            recharges = []
            for key in keys[:limit]:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                recharge_data = await self.payment_cache.get_payment_details(key_str)
                if recharge_data:
                    recharges.append(recharge_data)

            return {
                "status": "success",
                "recharges": recharges,
                "total": len(recharges)
            }
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    async def get_payment_history(self, user_id: int, limit: int = 10) -> Dict[str, Any]:
        """Получение истории платежей пользователя из кеша"""
        if not self.payment_cache:
            return {"error": "Payment cache not available", "status": "failed"}

        try:
            # Получаем все ключи платежей пользователя
            pattern = f"user_order:{user_id}:*"
            keys = await self.payment_cache.redis_client.execute_operation('keys', pattern)

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
            await self.payment_cache.redis_client.execute_operation('delete', cache_key)
            return True
        except Exception:
            return False

    async def get_payment_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получение статистики платежей пользователя"""
        if not self.payment_cache:
            return {"error": "Payment cache not available", "status": "failed"}

        try:
            pattern = f"user_order:{user_id}:*"
            keys = await self.payment_cache.redis_client.execute_operation('keys', pattern)

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

    def get_payment_message(self, payment_data: Dict[str, Any]) -> str:
        """
        Форматирование сообщения о платеже с использованием MessageFormatter.

        Args:
            payment_data: Данные о платеже для форматирования

        Returns:
            str: Отформатированное сообщение о платеже
        """
        if self.message_formatter:
            try:
                return self.message_formatter.format_payment(payment_data)
            except Exception as e:
                self.logger.error(f"Ошибка форматирования платежа через MessageFormatter: {e}")
                # Fallback к базовому форматированию
                return self._format_payment_fallback(payment_data)
        else:
            return self._format_payment_fallback(payment_data)

    def get_payment_status_message(self, status: str, amount: float, payment_id: Optional[str], currency: str = "TON") -> str:
        """
        Форматирование сообщения о статусе платежа с использованием MessageTemplate.

        Args:
            status: Статус платежа
            amount: Сумма платежа
            payment_id: ID платежа (опционально)
            currency: Валюта платежа

        Returns:
            str: Отформатированное сообщение о статусе платежа
        """
        try:
            return MessageTemplate.get_payment_status(status, amount, payment_id, currency)
        except Exception as e:
            self.logger.error(f"Ошибка форматирования статуса платежа: {e}")
            # Fallback к базовому форматированию
            return self._format_payment_status_fallback(status, amount, payment_id, currency)

    def get_recharge_message(self, amount: float, currency: str = "TON") -> str:
        """
        Форматирование сообщения о пополнении баланса.

        Args:
            amount: Сумма пополнения
            currency: Валюта пополнения

        Returns:
            str: Отформатированное сообщение о пополнении
        """
        try:
            formatted_amount = f"{amount:.2f}" if isinstance(amount, (int, float)) else str(amount)

            message = (
                f"{MessageTemplate.EMOJI_SUCCESS} <b>Баланс успешно пополнен!</b> {MessageTemplate.EMOJI_SUCCESS}\n\n"
                f"💰 <b>Пополнение:</b> {formatted_amount} {currency}\n"
                f"📅 <b>Дата:</b> {time.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"🌟 <i>Спасибо за пополнение!</i>\n"
                f"💎 <i>Ваши средства уже доступны для использования</i>"
            )

            return message
        except Exception as e:
            self.logger.error(f"Ошибка форматирования сообщения о пополнении: {e}")
            return f"✅ Баланс пополнен на {amount} {currency}"

    def _format_payment_fallback(self, payment_data: Dict[str, Any]) -> str:
        """
        Fallback форматирование платежа при отсутствии MessageFormatter.

        Args:
            payment_data: Данные о платеже

        Returns:
            str: Базовое форматирование платежа
        """
        try:
            amount = payment_data.get('amount', 'N/A')
            currency = payment_data.get('currency', 'TON')
            status = payment_data.get('status', 'unknown')
            payment_id = payment_data.get('payment_id', 'N/A')

            return (
                f"💳 <b>Информация о платеже</b>\n"
                f"💰 Сумма: {amount} {currency}\n"
                f"📊 Статус: {status}\n"
                f"🔢 ID: {payment_id}"
            )
        except Exception:
            return "💳 Информация о платеже недоступна"

    def _format_payment_status_fallback(self, status: str, amount: float, payment_id: Optional[str], currency: str = "TON") -> str:
        """
        Fallback форматирование статуса платежа.

        Args:
            status: Статус платежа
            amount: Сумма платежа
            payment_id: ID платежа
            currency: Валюта

        Returns:
            str: Базовое форматирование статуса платежа
        """
        try:
            formatted_amount = f"{amount:.2f}" if isinstance(amount, (int, float)) else str(amount)

            status_line = f"📊 Статус: {status}\n"
            amount_line = f"💰 Сумма: {formatted_amount} {currency}\n"

            message = f"{status_line}{amount_line}"

            if payment_id:
                message += f"🔢 ID платежа: {payment_id}\n"

            return message
        except Exception:
            return f"📊 Статус платежа: {status}"
