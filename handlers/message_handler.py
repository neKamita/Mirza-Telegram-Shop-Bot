"""
Централизованный диспетчер сообщений и колбэков для Telegram bot
"""
import logging
import re
from typing import Dict, Any, Optional, Union, List
from aiogram.types import Message, CallbackQuery
from aiogram import Bot, Dispatcher
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from .base_handler import BaseHandler
from .error_handler import ErrorHandler
from .balance_handler import BalanceHandler
from .payment_handler import PaymentHandler
from .purchase_handler import PurchaseHandler
from utils.message_templates import MessageTemplate
from utils.safe_message_edit import safe_edit_message
from utils.rate_limit_messages import RateLimitMessages


class MessageHandler(BaseHandler):
    """
    Централизованный диспетчер для обработки сообщений и колбэков
    
    Предоставляет единую точку входа для всех типов сообщений,
    делегируя обработку специализированным обработчикам.
    """

    def __init__(self, *args, **kwargs):
        """
        Инициализация диспетчера с интеграцией существующих обработчиков
        
        Args:
            *args: Аргументы для BaseHandler
            **kwargs: Ключевые аргументы для BaseHandler
        """
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)
        
        # Инициализация специализированных обработчиков через композицию
        self.error_handler = ErrorHandler(*args, **kwargs)
        self.balance_handler = BalanceHandler(*args, **kwargs)
        self.payment_handler = PaymentHandler(*args, **kwargs)
        self.purchase_handler = PurchaseHandler(*args, **kwargs)
        
        # Словарь для маршрутизации команд
        self.command_routes = {
            '/balance': self._handle_balance_command,
            '/payment': self._handle_payment_command,
            '/purchase': self._handle_purchase_command,
            '/start': self._handle_start_command,
            '/help': self._handle_help_command,
        }
        
        # Словарь для маршрутизации колбэков
        self.callback_routes = {
            'balance': self.balance_handler.show_balance,
            'balance_history': self.balance_handler.show_balance_history,
            'recharge': self.payment_handler.create_recharge,
            'check_recharge_': self.payment_handler.check_recharge_status,
            'buy_stars': self.purchase_handler.buy_stars_preset,
            'buy_': self.purchase_handler.buy_stars_preset,
            'buy_': self.purchase_handler.buy_stars_with_balance,
            'check_payment_': self.payment_handler.check_recharge_status,
        }

    async def handle_message(self, message: Message, bot: Bot) -> None:
        """
        Обработка текстовых сообщений с маршрутизацией по командам
        
        Args:
            message: Текстовое сообщение от пользователя
            bot: Экземпляр бота
        """
        if not message.text:
            await message.answer(MessageTemplate.get_unknown_command(), parse_mode="HTML")
            return
            
        # Валидация входящих данных
        if not await self._validate_input(message):
            return
            
        # Логирование события
        if message.from_user:
            await self._log_event("message", message.from_user.id, message.text)
        
        # Получение текста команды
        text = message.text.strip()
        
        # Маршрутизация по командам
        if text in self.command_routes:
            await self.command_routes[text](message, bot)
        else:
            # Проверка на числовые команды для покупки звезд
            if text.isdigit():
                amount = int(text)
                if 1 <= amount <= 10000:
                    await self.purchase_handler.buy_stars_custom(message, bot, amount)
                else:
                    await message.answer(MessageTemplate.get_error_message("validation", {"amount": amount}), parse_mode="HTML")
            else:
                # Обработка неизвестных команд
                await self._handle_unknown_command(message)

    async def handle_callback(self, callback: CallbackQuery, bot: Bot) -> None:
        """
        Обработка callback запросов с маршрутизацией по типам
        
        Args:
            callback: Callback запрос от пользователя
            bot: Экземпляр бота
        """
        if not callback.data:
            await callback.answer(MessageTemplate.get_unknown_callback(), show_alert=True)
            return
            
        # Валидация входящих данных
        if not await self._validate_input(callback):
            await callback.answer()
            return
            
        # Логирование события
        await self._log_event("callback", callback.from_user.id, callback.data)
        
        try:
            # Маршрутизация по колбэкам
            handled = False
            
            # Проверка на колбэки платежей
            if callback.data.startswith("check_recharge_"):
                payment_id = callback.data.replace("check_recharge_", "")
                await self.payment_handler.check_recharge_status(callback, bot, payment_id)
                handled = True
            elif callback.data.startswith("check_payment_"):
                payment_id = callback.data.replace("check_payment_", "")
                await self.payment_handler.check_recharge_status(callback, bot, payment_id)
                handled = True
            elif callback.data.startswith("cancel_recharge_"):
                payment_id = callback.data.replace("cancel_recharge_", "")
                await self.payment_handler.cancel_specific_recharge(callback, bot, payment_id)
                handled = True
            # Проверка на колбэки покупок звезд
            elif callback.data in ["buy_100", "buy_250", "buy_500", "buy_1000"]:
                amount = int(callback.data.replace("buy_", ""))
                await self.purchase_handler.buy_stars_preset(callback, bot, amount)
                handled = True
            elif callback.data in ["buy_100_balance", "buy_250_balance", "buy_500_balance", "buy_1000_balance"]:
                amount = int(callback.data.replace("buy_", "").replace("_balance", ""))
                await self.purchase_handler.buy_stars_with_balance(callback, bot, amount)
                handled = True
            # Проверка на колбэки пополнения
            elif callback.data in ["recharge_10", "recharge_50", "recharge_100", "recharge_500"]:
                amount = float(callback.data.replace("recharge_", ""))
                await self.payment_handler.create_recharge(callback, bot, amount)
                handled = True
            # Проверка на системные колбэки
            elif callback.data == "back_to_main":
                if callback.message:
                    await self._handle_start_command(callback, bot)
                handled = True
            elif callback.data == "help":
                if callback.message:
                    await self._handle_help_command(callback, bot)
                handled = True
            # Проверка на ошибки
            elif callback.data.startswith("error_action_"):
                await self.error_handler.handle_error_action(callback, bot)
                handled = True
            # Обработка колбэков баланса
            elif callback.data in ["balance", "balance_history"]:
                await self.balance_handler.handle_callback(callback, bot)
                handled = True
            # Обработка колбэков покупок
            elif callback.data in ["buy_stars", "buy_stars_balance", "back_to_buy_stars"]:
                await self.purchase_handler.handle_callback(callback, bot)
                handled = True
            # Обработка колбэков пополнения
            elif callback.data in ["recharge", "back_to_recharge", "recharge_custom"]:
                await self.payment_handler.handle_callback(callback, bot)
                handled = True
            # Обработка колбэка возврата к балансу
            elif callback.data == "back_to_balance":
                await self.balance_handler.show_balance(callback, bot)
                handled = True
                
            if not handled:
                await self._handle_unknown_callback(callback)
                
        except Exception as e:
            self.logger.error(f"Error handling callback {callback.data} for user {callback.from_user.id}: {e}")
            await self.error_handler.show_error_with_suggestions(
                callback,
                self.error_handler.categorize_error(str(e)),
                {"user_id": callback.from_user.id, "error": str(e)}
            )

    def register_handlers(self, dp: Dispatcher) -> None:
        """
        Регистрация обработчиков в dispatcher
        
        Args:
            dp: Экземпляр Dispatcher aiogram
        """
        # Регистрация обработчика сообщений
        dp.message.register(self.handle_message)
        
        # Регистрация обработчика callback запросов
        dp.callback_query.register(self.handle_callback)
        
        self.logger.info("Message handlers registered successfully")

    async def _validate_input(self, message_or_callback: Union[Message, CallbackQuery]) -> bool:
        """
        Валидация входящих данных для безопасности
        
        Args:
            message_or_callback: Сообщение или callback запрос
            
        Returns:
            True если данные валидны, False в противном случае
        """
        try:
            # Проверка наличия пользователя
            if not message_or_callback.from_user or not message_or_callback.from_user.id:
                self.logger.warning("Message or callback has no user information")
                return False
            user_id = message_or_callback.from_user.id
            
            # Проверка пользователя в базе данных
            if not await self.validate_user(user_id):
                self.logger.error(f"User validation failed for {user_id}")
                return False
                
            # Проверка rate limiting с новой системой (30 сообщений в минуту = 2 секунды между сообщениями)
            if not await self.check_rate_limit(user_id, "message", 30, 60):
                self.logger.warning(f"Rate limit exceeded for user {user_id}")
                # Показываем пользователю сообщение о превышении лимита
                await self._show_rate_limit_message(message_or_callback, "message")
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"Error during input validation: {e}")
            return False

    async def _log_event(self, event_type: str, user_id: int, data: str) -> None:
        """
        Логирование важных событий
        
        Args:
            event_type: Тип события (message, callback, etc.)
            user_id: ID пользователя
            data: Данные события
        """
        try:
            # Обрезаем длинные данные для логирования
            log_data = data[:200] + "..." if len(data) > 200 else data
            
            self.logger.info(
                f"Event - Type: {event_type}, User: {user_id}, Data: {log_data}"
            )
            
            # Дополнительное логирование для критичных событий
            if event_type == "callback" and any(keyword in data for keyword in 
                                              ["payment", "recharge", "buy", "balance"]):
                self.logger.info(
                    f"Critical event - User: {user_id}, Action: {data}"
                )
                
        except Exception as e:
            self.logger.error(f"Error logging event: {e}")

    async def _handle_balance_command(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot) -> None:
        """Обработка команды /balance"""
        await self.balance_handler.show_balance(message_or_callback, bot)

    async def _handle_payment_command(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot) -> None:
        """Обработка команды /payment"""
        await self.payment_handler.show_recharge_menu(message_or_callback, bot)

    async def _handle_purchase_command(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot) -> None:
        """Обработка команды /purchase"""
        # Показываем меню покупок
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="💳 Картой/Кошельком", callback_data="buy_stars"),
            InlineKeyboardButton(text="💰 С баланса", callback_data="buy_stars_balance")
        )
        builder.row(
            InlineKeyboardButton(text="💎 Через Fragment", callback_data="buy_stars_fragment")
        )
        builder.row(
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
        )
        
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(
                "⭐ <b>Покупка звезд</b> ⭐\n\n"
                "🎯 <i>Выберите способ оплаты:</i>\n\n"
                f"💳 <i>Картой/Кошельком - оплата через Heleket</i>\n"
                f"💰 <i>С баланса - списание со счета</i>\n"
                f"💎 <i>Через Fragment - прямая покупка</i>\n\n"
                f"✨ <i>Каждая звезда имеет ценность!</i>",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        else:
            if isinstance(message_or_callback, CallbackQuery) and message_or_callback.message:
                success = await safe_edit_message(
                    message_or_callback.message,
                    MessageTemplate.get_purchase_menu_title(),
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
                if not success:
                    self.logger.error("Failed to edit purchase menu message")

    async def _handle_start_command(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot) -> None:
        """Обработка команды /start"""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
            InlineKeyboardButton(text="⭐ Купить звезды", callback_data="buy_stars")
        )
        builder.row(
            InlineKeyboardButton(text="📊 История", callback_data="balance_history"),
            InlineKeyboardButton(text="❓ Помощь", callback_data="help")
        )
        
        welcome_message = MessageTemplate.get_welcome_message()
        
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(
                welcome_message,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        else:
            if isinstance(message_or_callback, CallbackQuery) and message_or_callback.message:
                success = await safe_edit_message(
                    message_or_callback.message,
                    welcome_message,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
                if not success:
                    self.logger.error("Failed to edit start menu message")

    async def _handle_help_command(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot) -> None:
        """Обработка команды /help"""
        help_message = MessageTemplate.get_help_message()
        
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(help_message, parse_mode="HTML")
        else:
            if isinstance(message_or_callback, CallbackQuery) and message_or_callback.message:
                success = await safe_edit_message(
                    message_or_callback.message,
                    help_message,
                    parse_mode="HTML"
                )
                if not success:
                    self.logger.error("Failed to edit help message")

    async def _handle_unknown_command(self, message: Message) -> None:
        """Обработка неизвестных текстовых команд"""
        await message.answer(MessageTemplate.get_unknown_command(), parse_mode="HTML")

    async def _handle_unknown_callback(self, callback: CallbackQuery) -> None:
        """Обработка неизвестных callback запросов"""
        await callback.answer(MessageTemplate.get_unknown_callback(), show_alert=True)

    async def _show_rate_limit_message(self, message_or_callback: Union[Message, CallbackQuery], limit_type: str) -> None:
        """
        Показ сообщения о превышении rate limit пользователю
        
        Args:
            message_or_callback: Сообщение или callback запрос
            limit_type: Тип лимита
        """
        try:
            if not message_or_callback.from_user or not message_or_callback.from_user.id:
                return
            user_id = message_or_callback.from_user.id
            remaining_time = await self.get_rate_limit_remaining_time(user_id, limit_type)
            # DEBUG: Логирование для диагностики проблемы типизации
            self.logger.debug(f"DEBUG: remaining_time type: {type(remaining_time)}, value: {remaining_time}")
            self.logger.debug(f"DEBUG: remaining_time is None: {remaining_time is None}")
            
            if isinstance(message_or_callback, Message):
                rate_limit_message = RateLimitMessages.get_rate_limit_message(limit_type, remaining_time, for_callback=False)
                await message_or_callback.answer(rate_limit_message, parse_mode="HTML")
            elif isinstance(message_or_callback, CallbackQuery):
                rate_limit_message = RateLimitMessages.get_rate_limit_message(limit_type, remaining_time, for_callback=True)
                await message_or_callback.answer(rate_limit_message, show_alert=True)
                
        except Exception as e:
            self.logger.error(f"Error showing rate limit message: {e}")