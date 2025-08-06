"""
Сервис для работы с платежной системой
"""
import json
import hashlib
import base64
import aiohttp
from typing import Dict, Any
from core.interfaces import PaymentInterface


class PaymentService(PaymentInterface):
    """Сервис для управления платежами"""

    def __init__(self, merchant_uuid: str, api_key: str):
        self.merchant_uuid = merchant_uuid
        self.api_key = api_key

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
        """Создание счета на оплату"""
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
                    "https://api.heleket.com/v1/payment",
                    headers=headers,
                    data=json_data
                ) as response:
                    return await response.json()
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    async def check_payment(self, invoice_uuid: str) -> Dict[str, Any]:
        """Проверка статуса оплаты"""
        payload = {"uuid": invoice_uuid}
        json_data = json.dumps(payload)
        headers = self._generate_headers(json_data)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.heleket.com/v1/payment/info",
                    headers=headers,
                    data=json_data
                ) as response:
                    return await response.json()
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    async def create_invoice_for_user(self, user_id: int) -> Dict[str, Any]:
        """Создание счета для конкретного пользователя"""
        order_id = f"subscription-{user_id}-{int(__import__('time').time())}"
        return await self.create_invoice(
            amount="1",
            currency="TON",
            order_id=order_id
        )
