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
