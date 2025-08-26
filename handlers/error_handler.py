"""
Обработчик ошибок для всех операций системы
"""
import logging
from enum import Enum
from typing import Dict, Any, Optional, List

from aiogram.types import Message, CallbackQuery, InaccessibleMessage
from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from .base_handler import BaseHandler
from services.balance.balance_service import BalanceService
from utils.message_templates import MessageTemplate


class PurchaseErrorType(Enum):
    """Типы ошибок при покупке"""
    INSUFFICIENT_BALANCE = "insufficient_balance"
    NETWORK_ERROR = "network_error"
    PAYMENT_SYSTEM_ERROR = "payment_system_error"
    VALIDATION_ERROR = "validation_error"
    SYSTEM_ERROR = "system_error"
    UNKNOWN_ERROR = "unknown_error"
    TRANSACTION_FAILED = "transaction_failed"


class ErrorHandler(BaseHandler):
    """
    Обработчик ошибок с наследованием от BaseHandler
    Предоставляет универсальную обработку ошибок покупок и других операций
    """

    def __init__(self, *args, **kwargs):
        """
        Инициализация обработчика ошибок
        """
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)

    def categorize_error(self, error_message: str) -> PurchaseErrorType:
        """
        Категоризация ошибки по типу с улучшенной точностью
        
        Args:
            error_message: Сообщение об ошибке
            
        Returns:
            Категория ошибки
        """
        error_message = error_message.lower()
        
        # Проверяем на недостаток средств с различными вариациями
        insufficient_balance_patterns = [
            "insufficient balance", "недостаточно средств", "недостаточно баланса",
            "not enough balance", "balance too low", "funds insufficient",
            "недостаточно денег", "не хватает средств", "баланс недостаточен"
        ]
        
        # Проверяем на сетевые ошибки
        network_error_patterns = [
            "network", "сеть", "connection", "подключение", "timeout",
            "unreachable", "network error", "connection failed", "no connection"
        ]
        
        # Проверяем на ошибки платежной системы
        payment_error_patterns = [
            "payment", "платеж", "heleket", "payment system", "processing",
            "declined", "failed", "error", "ошибка", "transaction failed"
        ]
        
        # Проверяем на ошибки валидации
        validation_error_patterns = [
            "validation", "валидация", "invalid", "некорректный", "неправильный",
            "format", "format error", "invalid input", "wrong format"
        ]
        
        # Проверяем на ошибки транзакций
        transaction_error_patterns = [
            "transaction", "транзакция", "tx", "transfer", "send",
            "transaction failed", "tx failed", "transfer failed"
        ]
        
        # Проверяем на системные ошибки
        system_error_patterns = [
            "system", "система", "internal", "внутренний", "server",
            "database", "db", "500", "error 500", "service unavailable"
        ]
        
        # Проверяем в определенном порядке для приоритетной обработки
        for pattern in insufficient_balance_patterns:
            if pattern in error_message:
                return PurchaseErrorType.INSUFFICIENT_BALANCE
                
        for pattern in network_error_patterns:
            if pattern in error_message:
                return PurchaseErrorType.NETWORK_ERROR
                
        for pattern in payment_error_patterns:
            if pattern in error_message:
                return PurchaseErrorType.PAYMENT_SYSTEM_ERROR
                
        for pattern in validation_error_patterns:
            if pattern in error_message:
                return PurchaseErrorType.VALIDATION_ERROR
                
        for pattern in transaction_error_patterns:
            if pattern in error_message:
                return PurchaseErrorType.TRANSACTION_FAILED
                
        for pattern in system_error_patterns:
            if pattern in error_message:
                return PurchaseErrorType.SYSTEM_ERROR
        
        # Если ни одна из категорий не подошла
        return PurchaseErrorType.UNKNOWN_ERROR

    def get_error_message(self, error_type: PurchaseErrorType, context: Optional[dict] = None) -> str:
        """
        Получение user-friendly сообщения об ошибке с контекстом и рекомендациями
        
        Args:
            error_type: Тип ошибки
            context: Контекст ошибки
            
        Returns:
            Форматированное сообщение об ошибке
        """
        context = context or {}
        
        # Получаем общие данные из контекста
        user_id = context.get('user_id', 'неизвестный')
        amount = context.get('amount', 0)
        # Обработка случая, когда amount равен None
        if amount is None:
            amount = 0
        payment_id = context.get('payment_id', 'неизвестен')
        error_detail = context.get('error', 'Неизвестная ошибка')
        
        # Используем MessageTemplate для генерации сообщений об ошибках
        error_mapping = {
            PurchaseErrorType.INSUFFICIENT_BALANCE: 'validation',
            PurchaseErrorType.NETWORK_ERROR: 'network',
            PurchaseErrorType.PAYMENT_SYSTEM_ERROR: 'payment',
            PurchaseErrorType.VALIDATION_ERROR: 'validation',
            PurchaseErrorType.TRANSACTION_FAILED: 'payment',
            PurchaseErrorType.SYSTEM_ERROR: 'system',
            PurchaseErrorType.UNKNOWN_ERROR: 'unknown'
        }
        
        template_error_type = error_mapping.get(error_type, 'unknown')
        context['error'] = error_detail
        context['payment_id'] = payment_id
        
        return MessageTemplate.get_error_message(template_error_type, context)

    def get_suggested_actions(self, error_type: PurchaseErrorType) -> List[tuple]:
        """
        Получение детализированных рекомендованных действий в зависимости от типа ошибки
        
        Args:
            error_type: Тип ошибки
            
        Returns:
            Список кортежей (текст_кнопки, callback_data)
        """
        actions = {
            PurchaseErrorType.INSUFFICIENT_BALANCE: [
                ("💳 Пополнить баланс", "recharge"),
                ("⭐ Выбрать меньшую сумму", "reduce_amount"),
                ("💰 Использовать другой способ оплаты", "alternative_payment")
            ],
            PurchaseErrorType.NETWORK_ERROR: [
                ("📡 Проверить интернет-соединение", "check_connection"),
                ("🔄 Попробовать снова через 30 секунд", "retry_later"),
                ("📱 Переключиться на другую сеть", "change_network")
            ],
            PurchaseErrorType.PAYMENT_SYSTEM_ERROR: [
                ("⏰ Попробовать снова через 5 минут", "retry_delayed"),
                ("💳 Использовать другой способ оплаты", "alternative_payment"),
                ("💱 Попробовать другую валюту", "change_currency")
            ],
            PurchaseErrorType.VALIDATION_ERROR: [
                ("✅ Проверить введенные данные", "check_input"),
                ("📏 Убедиться в корректности суммы", "validate_amount"),
                ("🔢 Ввести корректное значение", "correct_input")
            ],
            PurchaseErrorType.TRANSACTION_FAILED: [
                ("🔄 Попробовать снова", "retry"),
                ("💳 Проверить баланс карты/кошелька", "check_balance"),
                ("📱 Убедиться в разрешении платежа", "check_permission")
            ],
            PurchaseErrorType.SYSTEM_ERROR: [
                ("⏰ Попробовать снова позже", "retry_later"),
                ("🔄 Обновить приложение или страницу", "refresh"),
                ("📱 Очистить кеш браузера", "clear_cache")
            ],
            PurchaseErrorType.UNKNOWN_ERROR: [
                ("🔄 Попробовать снова", "retry"),
                ("📱 Перезапустить приложение", "restart"),
                ("🔄 Обновить страницу", "refresh")
            ]
        }
        
        # Возвращаем и тексты кнопок, и callback_data
        return actions.get(error_type, [("🔄 Попробовать снова", "retry"), ("📞 Обратиться в поддержку", "support")])

    async def handle_purchase_error(self, error: Exception, context: Optional[dict] = None) -> PurchaseErrorType:
        """
        Обработка ошибок покупок с категоризацией и улучшенным логированием
        
        Args:
            error: Исключение
            context: Контекст ошибки
            
        Returns:
            Тип ошибки
        """
        error_message = str(error)
        error_type = self.categorize_error(error_message)
        
        # Получаем контекстные данные для логирования
        user_id = context.get('user_id', 'unknown') if context else 'unknown'
        amount = context.get('amount', 0) if context else 0
        payment_id = context.get('payment_id', 'unknown') if context else 'unknown'
        
        # Улучшенное логирование с контекстом
        self.logger.error(
            f"Purchase error occurred - User: {user_id}, Amount: {amount}, PaymentID: {payment_id}, "
            f"ErrorType: {error_type.value}, ErrorMessage: {error_message}"
        )
        
        # Дополнительное логирование для критических ошибок
        if error_type in [PurchaseErrorType.INSUFFICIENT_BALANCE, PurchaseErrorType.SYSTEM_ERROR, PurchaseErrorType.UNKNOWN_ERROR]:
            self.logger.critical(
                f"Critical purchase error - User: {user_id}, ErrorType: {error_type.value}, "
                f"ErrorMessage: {error_message}"
            )
        
        return error_type

    async def show_error_with_suggestions(self, message: Message | CallbackQuery, error_type: PurchaseErrorType, context: Optional[dict] = None) -> None:
        """
        Показ ошибки с рекомендациями действий и улучшенной навигацией
        
        Args:
            message: Сообщение или callback
            error_type: Тип ошибки
            context: Контекст ошибки
        """
        error_message = self.get_error_message(error_type, context)
        suggested_actions = self.get_suggested_actions(error_type)
        
        # Создаем клавиатуру с рекомендованными действиями
        builder = InlineKeyboardBuilder()
        
        # Добавляем кнопки с рекомендованными действиями
        for action_text, action_callback in suggested_actions[:3]:  # Максимум 3 кнопки
            builder.row(InlineKeyboardButton(text=f"🔧 {action_text}", callback_data=f"error_action_{action_callback}"))
        
        # Кнопка возврата в логическое меню
        if isinstance(message, CallbackQuery):
            builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_main"))
        else:
            builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_main"))
        
        # Кнопка помощи
        builder.row(InlineKeyboardButton(text="❓ Помощь", callback_data="help"))
        
        # Определяем, как отправить сообщение
        if isinstance(message, Message):
            await message.answer(error_message, reply_markup=builder.as_markup(), parse_mode="HTML")
        elif isinstance(message, CallbackQuery) and message.message:
            # Проверяем, доступно ли сообщение для редактирования
            if isinstance(message.message, InaccessibleMessage):
                # Сообщение недоступно, отправляем новое
                await message.answer(error_message, show_alert=True)
            else:
                try:
                    await message.message.edit_text(error_message, reply_markup=builder.as_markup(), parse_mode="HTML")
                except TelegramBadRequest as e:
                    self.logger.error(f"TelegramBadRequest while editing message: {e}")
                    # Если редактирование невозможно, отправляем новое сообщение
                    await message.answer(error_message, show_alert=True)
                except Exception as e:
                    self.logger.error(f"Unexpected error editing message: {e}")
                    await message.answer(error_message, show_alert=True)

    async def handle_error_action(self, callback: CallbackQuery, bot: Bot) -> None:
        """
        Обработка действий после ошибок
        
        Args:
            callback: Callback запрос
            bot: Экземпляр бота
        """
        await callback.answer()
        
        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id

        if not callback.data:
            return

        action = callback.data.replace("error_action_", "")
        
        self.logger.info(f"User {user_id} selected error action: {action}")
        
        # Обработка различных действий после ошибок
        if action == "recharge":
            # Перенаправление на пополнение баланса
            # Здесь можно вызвать соответствующий метод из другого обработчика
            if callback.message:
                await callback.message.answer("🔄 <b>Перенаправление на пополнение баланса</b> 🔄\n\n"
                                            "💳 <i>Вы будете перенаправлены в меню пополнения</i>\n\n"
                                            "💡 <i>Подождите...</i>",
                                            parse_mode="HTML")
            else:
                await callback.answer("🔄 Перенаправление на пополнение баланса\n\n"
                                    "💳 Вы будете перенаправлены в меню пополнения\n\n"
                                    "💡 Подождите...",
                                    show_alert=True)
        elif action == "reduce_amount":
            # Показываем меню покупки звезд с меньшими суммами
            if callback.message:
                await callback.message.answer("⭐ <b>Меню покупки звезд</b> ⭐\n\n"
                                            "🎯 <i>Выберите пакет с меньшей суммой</i>\n\n"
                                            "💡 <i>Подождите перенаправления...</i>",
                                            parse_mode="HTML")
            else:
                await callback.answer("⭐ Меню покупки звезд\n\n"
                                    "🎯 Выберите пакет с меньшей суммой\n\n"
                                    "💡 Подождите перенаправления...",
                                    show_alert=True)
        elif action == "alternative_payment":
            # Показываем меню с альтернативными способами оплаты
            if callback.message:
                await callback.message.answer("💳 <b>Альтернативные способы оплаты</b> 💳\n\n"
                                            "🔄 <i>Выберите другой способ оплаты</i>\n\n"
                                            "💡 <i>Подождите перенаправления...</i>",
                                            parse_mode="HTML")
            else:
                await callback.answer("💳 Альтернативные способы оплаты\n\n"
                                    "🔄 Выберите другой способ оплаты\n\n"
                                    "💡 Подождите перенаправления...",
                                    show_alert=True)
        elif action == "check_connection":
            # Показываем сообщение о проверке соединения
            if callback.message:
                await callback.message.answer("📡 <b>Проверьте интернет-соединение</b> 📡\n\n"
                                            "🔍 <i>Убедитесь, что у вас есть стабильное подключение к интернету</i>\n\n"
                                            "🔄 <i>Попробуйте снова через 30 секунд</i>\n\n"
                                            "💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                                            parse_mode="HTML")
            else:
                await callback.answer("📡 Проверьте интернет-соединение\n\n"
                                    "🔍 Убедитесь, что у вас есть стабильное подключение к интернету\n\n"
                                    "🔄 Попробуйте снова через 30 секунд\n\n"
                                    "💡 Если проблема сохраняется, обратитесь в поддержку",
                                    show_alert=True)
        elif action == "retry_later":
            # Показываем сообщение о повторной попытке
            if callback.message:
                await callback.message.answer("⏰ <b>Попробуйте снова позже</b> ⏰\n\n"
                                            "🔄 <i>Система временно недоступна</i>\n\n"
                                            "⏳ <i>Попробуйте обновить страницу через 5 минут</i>\n\n"
                                            "💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                                            parse_mode="HTML")
            else:
                await callback.answer("⏰ Попробуйте снова позже\n\n"
                                    "🔄 Система временно недоступна\n\n"
                                    "⏳ Попробуйте обновить страницу через 5 минут\n\n"
                                    "💡 Если проблема сохраняется, обратитесь в поддержку",
                                    show_alert=True)
        elif action == "retry":
            # Показываем сообщение о повторной попытке
            if callback.message:
                await callback.message.answer("🔄 <b>Повторная попытка</b> 🔄\n\n"
                                            "⚡ <i>Система пытается обработать ваш запрос снова</i>\n\n"
                                            "🔧 <i>Это может занять несколько секунд</i>\n\n"
                                            "💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                                            parse_mode="HTML")
            else:
                await callback.answer("🔄 Повторная попытка\n\n"
                                    "⚡ Система пытается обработать ваш запрос снова\n\n"
                                    "🔧 Это может занять несколько секунд\n\n"
                                    "💡 Если проблема сохраняется, обратитесь в поддержку",
                                    show_alert=True)
        elif action == "support":
            # Показываем экран помощи
            from config.settings import settings
            if callback.message:
                await callback.message.answer("🤖 <b>Помощь и поддержка</b> 🤖\n\n"
                                            "📞 <i>Свяжитесь с нашей поддержкой для решения проблемы</i>\n\n"
                                            f"👤 <i>Контакт: {settings.support_contact}</i>\n\n"
                                            "⏰ <i>Ответ в течение 24 часов</i>",
                                            parse_mode="HTML")
            else:
                await callback.answer("🤖 Помощь и поддержка\n\n"
                                    "📞 Свяжитесь с нашей поддержкой для решения проблемы\n\n"
                                    f"👤 Контакт: {settings.support_contact}\n\n"
                                    "⏰ Ответ в течение 24 часов",
                                    show_alert=True)
        else:
            # По умолчанию возвращаем в главное меню
            if callback.message:
                await callback.message.answer("🔄 <b>Возврат в главное меню</b> 🔄\n\n"
                                            "🏠 <i>Вы будете перенаправлены в главное меню</i>\n\n"
                                            "💡 <i>Подождите...</i>",
                                            parse_mode="HTML")
            else:
                await callback.answer("🔄 Возврат в главное меню\n\n"
                                    "🏠 Вы будете перенаправлены в главное меню\n\n"
                                    "💡 Подождите...",
                                    show_alert=True)

    async def handle_message(self, message: Message, bot: Bot) -> None:
        """
        Обработка текстовых сообщений (реализация абстрактного метода)
        """
        self.logger.info(f"Error handling message from user {message.from_user.id if message.from_user else 'unknown'}")
        
        # Обработка сообщений об ошибках
        if message.text and "ошибка" in message.text.lower():
            await self.show_error_with_suggestions(
                message, 
                PurchaseErrorType.UNKNOWN_ERROR, 
                {"user_id": message.from_user.id if message.from_user else "unknown", "error": "Запрос помощи"}
            )
        else:
            await message.answer("❓ <b>Неизвестная команда</b> ❓\n\n"
                               "🔍 <i>Пожалуйста, используйте доступные команды</i>\n\n"
                               "💡 <i>Введите /start для возврата в меню</i>",
                               parse_mode="HTML")

    async def handle_callback(self, callback: CallbackQuery, bot: Bot) -> None:
        """
        Обработка callback запросов (реализация абстрактного метода)
        """
        self.logger.info(f"Error handling callback from user {callback.from_user.id if callback.from_user else 'unknown'}")
        
        # Обработка callback, связанных с ошибками
        if callback.data == "error_action_support":
            await self.show_error_with_suggestions(
                callback,
                PurchaseErrorType.UNKNOWN_ERROR,
                {"user_id": callback.from_user.id if callback.from_user else "unknown", "error": "Запрос поддержки"}
            )
        else:
            await callback.answer("❓ <b>Неизвестное действие</b> ❓\n\n"
                               "🔍 <i>Пожалуйста, используйте доступные кнопки</i>\n\n"
                               "💡 <i>Введите /start для возврата в меню</i>",
                               show_alert=True)