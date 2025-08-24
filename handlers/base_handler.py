"""
Базовый класс для всех обработчиков с общей логикой и зависимостями
"""
import logging
from abc import ABC
from typing import Any, Dict, Optional, Union

from aiogram.types import Message, CallbackQuery
from aiogram import Bot
from core.interfaces import EventHandlerInterface
from repositories.user_repository import UserRepository
from services.payment import PaymentService
from services.payment import BalanceService
from services.payment import StarPurchaseService
from services.cache import SessionCache
from services.cache import RateLimitCache
from services.cache import PaymentCache


class BaseHandler(EventHandlerInterface, ABC):
    """
    Базовый класс для всех обработчиков с общей логикой обработки сообщений и callback.
    Предоставляет общие методы для проверки rate limit, безопасного выполнения и управления сессиями.
    """

    def __init__(self,
                 user_repository: UserRepository,
                 payment_service: PaymentService,
                 balance_service: BalanceService,
                 star_purchase_service: StarPurchaseService,
                 session_cache: Optional[SessionCache] = None,
                 rate_limit_cache: Optional[RateLimitCache] = None,
                 payment_cache: Optional[PaymentCache] = None):
        """
        Инициализация базового обработчика с основными зависимостями
        
        Args:
            user_repository: Репозиторий для работы с пользователями
            payment_service: Сервис для работы с платежами
            balance_service: Сервис для работы с балансом
            star_purchase_service: Сервис для покупки звезд
            session_cache: Кеш сессий (опционально)
            rate_limit_cache: Кеш для ограничения запросов (опционально)
            payment_cache: Кеш платежей (опционально)
        """
        self.user_repository = user_repository
        self.payment_service = payment_service
        self.balance_service = balance_service
        self.star_purchase_service = star_purchase_service
        self.session_cache = session_cache
        self.rate_limit_cache = rate_limit_cache
        self.payment_cache = payment_cache
        self.logger = logging.getLogger(__name__)

    async def check_rate_limit(self, user_id: int, limit_type: str, max_requests: int, time_window: int) -> bool:
        """
        Проверка ограничения частоты запросов для пользователя
        
        Args:
            user_id: ID пользователя
            limit_type: Тип запроса ('message', 'callback', 'payment')
            max_requests: Максимальное количество запросов
            time_window: Временное окно в секундах
            
        Returns:
            True если запрос разрешен, False если превышен лимит
        """
        if not self.rate_limit_cache:
            return True

        try:
            allowed = await self.rate_limit_cache.check_user_rate_limit(
                user_id, limit_type, max_requests, time_window
            )
            
            if not allowed:
                self.logger.warning(f"Rate limit exceeded for user {user_id}, type: {limit_type}")
            
            return allowed
        except Exception as e:
            self.logger.error(f"Error checking rate limit for user {user_id}: {e}")
            return True  # В случае ошибки разрешаем запрос

    async def get_rate_limit_remaining_time(self, user_id: int, limit_type: str) -> int:
        """
        Получение оставшегося времени до сброса rate limit
        
        Args:
            user_id: ID пользователя
            limit_type: Тип лимита
            
        Returns:
            Оставшееся время в секундах
        """
        if not self.rate_limit_cache:
            return 0
            
        try:
            info = await self.rate_limit_cache.get_rate_limit_info(
                str(user_id), limit_type, window=60, limit=10
            )
            if info and info.get('reset_time'):
                from datetime import datetime
                reset_time = info['reset_time']
                if isinstance(reset_time, str):
                    reset_time = datetime.fromisoformat(reset_time)
                remaining = (reset_time - datetime.utcnow()).total_seconds()
                return max(0, int(remaining))
            return 60  # Возвращаем стандартное время окна
        except Exception as e:
            self.logger.error(f"Error getting rate limit remaining time: {e}")
            return 60

    async def safe_execute(self, 
                          user_id: int, 
                          operation: str,
                          func: callable,
                          *args, 
                          **kwargs) -> Any:
        """
        Безопасное выполнение операции с обработкой ошибок и валидацией
        
        Args:
            user_id: ID пользователя
            operation: Описание операции для логирования
            func: Функция для выполнения
            *args: Аргументы функции
            **kwargs: Ключевые аргументы функции
            
        Returns:
            Результат выполнения функции или None в случае ошибки
        """
        try:
            self.logger.debug(f"Executing {operation} for user {user_id}")
            
            # Проверка rate limit перед выполнением (20 операций в минуту = 3 секунды между операциями)
            if not await self.check_rate_limit(user_id, "operation", 20, 60):
                self.logger.warning(f"Rate limit check failed for operation {operation} by user {user_id}")
                return None
            
            # Выполнение функции
            result = await func(*args, **kwargs)
            
            self.logger.debug(f"Successfully executed {operation} for user {user_id}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error during {operation} for user {user_id}: {e}", exc_info=True)
            return None

    async def manage_session(self, user_id: int, session_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Управление сессией пользователя
        
        Args:
            user_id: ID пользователя
            session_data: Данные для создания сессии (опционально)
            
        Returns:
            Данные сессии или None
        """
        if not self.session_cache:
            return None

        try:
            if session_data:
                # Создание новой сессии
                await self.session_cache.create_session(user_id, session_data)
                self.logger.info(f"Created new session for user {user_id}")
                return session_data
            else:
                # Получение существующей сессии
                user_sessions = await self.session_cache.get_user_sessions(user_id)
                if user_sessions:
                    self.logger.debug(f"Found existing session for user {user_id}")
                    return user_sessions[0]
                else:
                    self.logger.debug(f"No existing session found for user {user_id}")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Error managing session for user {user_id}: {e}")
            return None

    async def validate_user(self, user_id: int) -> bool:
        """
        Валидация пользователя (проверка существования в базе данных)
        
        Args:
            user_id: ID пользователя
            
        Returns:
            True если пользователь существует или успешно создан
        """
        try:
            exists = await self.user_repository.user_exists(user_id)
            if not exists:
                # Создаем пользователя если не существует
                success = await self.user_repository.add_user(user_id)
                if success:
                    self.logger.info(f"Created new user {user_id}")
                    return True
                else:
                    self.logger.error(f"Failed to create user {user_id}")
                    return False
            return True
        except Exception as e:
            self.logger.error(f"Error validating user {user_id}: {e}")
            return False

    def get_user_info_from_message(self, message: Union[Message, CallbackQuery]) -> Optional[Dict[str, Any]]:
        """
        Извлечение информации о пользователе из сообщения или callback
        
        Args:
            message: Сообщение или callback
            
        Returns:
            Словарь с информацией о пользователе или None
        """
        if not message.from_user or not message.from_user.id:
            self.logger.warning("Message or callback has no user information")
            return None

        return {
            "id": message.from_user.id,
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
            "is_bot": message.from_user.is_bot
        }

    def format_error_response(self, error: Exception, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Форматирование сообщения об ошибке для пользователя
        
        Args:
            error: Исключение
            context: Контекст ошибки
            
        Returns:
            Отформатированное сообщение об ошибке
        """
        error_message = str(error)
        user_id = context.get('user_id', 'unknown') if context else 'unknown'
        
        self.logger.error(f"Error occurred for user {user_id}: {error_message}")
        
        # Базовое сообщение об ошибке
        base_message = (
            "❌ <b>Произошла ошибка</b> ❌\n\n"
            f"🔍 <i>Ошибка: {error_message}</i>\n\n"
            f"👤 <i>Пользователь: {user_id}</i>\n\n"
            f"🔄 <i>Попробуйте позже или обратитесь в поддержку</i>"
        )
        
        return base_message

    async def handle_message(self, message: Message, bot: Bot) -> None:
        """
        Абстрактный метод обработки текстового сообщения
        Должен быть реализован в дочерних классах
        """
        raise NotImplementedError("Subclasses must implement handle_message method")

    async def handle_callback(self, callback: CallbackQuery, bot: Bot) -> None:
        """
        Абстрактный метод обработки callback запроса
        Должен быть реализован в дочерних классах
        """
        raise NotImplementedError("Subclasses must implement handle_callback method")