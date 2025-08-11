"""
Абстракции и интерфейсы для обеспечения SOLID принципов
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from aiogram.types import Message, CallbackQuery
from aiogram import Bot, Dispatcher


class DatabaseInterface(ABC):
    """Интерфейс для работы с базой данных"""

    @abstractmethod
    async def create_tables(self) -> None:
        """Создание таблиц в базе данных"""
        pass

    @abstractmethod
    async def add_user(self, user_id: int) -> bool:
        """Добавление пользователя в базу данных"""
        pass

    @abstractmethod
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользователя по ID"""
        pass

    @abstractmethod
    async def user_exists(self, user_id: int) -> bool:
        """Проверка существования пользователя"""
        pass


class PaymentInterface(ABC):
    """Интерфейс для работы с платежной системой"""

    @abstractmethod
    async def create_invoice(self, amount: str, currency: str, order_id: str) -> Dict[str, Any]:
        """Создание счета на оплату"""
        pass

    @abstractmethod
    async def check_payment(self, invoice_uuid: str) -> Dict[str, Any]:
        """Проверка статуса оплаты"""
        pass


# AIServiceInterface был удален как неиспользуемый


class BalanceServiceInterface(ABC):
    """Интерфейс для сервиса баланса"""

    @abstractmethod
    async def get_user_balance(self, user_id: int) -> Dict[str, Any]:
        """Получение баланса пользователя"""
        pass

    @abstractmethod
    async def update_user_balance(self, user_id: int, amount: float, operation: str = "add") -> bool:
        """Обновление баланса пользователя"""
        pass

    @abstractmethod
    async def get_user_transactions(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Получение транзакций пользователя"""
        pass

    @abstractmethod
    async def create_transaction(self, user_id: int, transaction_type: str, amount: float,
                                description: Optional[str] = None, external_id: Optional[str] = None,
                                metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """Создание транзакции"""
        pass

    @abstractmethod
    async def process_recharge(self, user_id: int, amount: float, payment_uuid: str) -> bool:
        """Обработка пополнения баланса"""
        pass

    @abstractmethod
    async def get_recharge_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение истории пополнений баланса"""
        pass


class StarPurchaseServiceInterface(ABC):
    """Интерфейс для сервиса покупки звезд"""

    @abstractmethod
    async def create_star_purchase(self, user_id: int, amount: int) -> Dict[str, Any]:
        """Создание покупки звезд"""
        pass

    @abstractmethod
    async def check_purchase_status(self, purchase_id: str) -> Dict[str, Any]:
        """Проверка статуса покупки"""
        pass

    @abstractmethod
    async def process_payment_webhook(self, webhook_data: Dict[str, Any]) -> bool:
        """Обработка вебхука от платежной системы"""
        pass

    @abstractmethod
    async def get_purchase_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение истории покупок пользователя"""
        pass


class EventHandlerInterface(ABC):
    """Интерфейс для обработчиков событий"""

    @abstractmethod
    async def handle_message(self, message: Message, bot: Bot) -> None:
        """Обработка текстового сообщения"""
        pass

    @abstractmethod
    async def handle_callback(self, callback: CallbackQuery, bot: Bot) -> None:
        """Обработка callback запроса"""
        pass
