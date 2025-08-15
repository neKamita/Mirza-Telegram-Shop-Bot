"""
Обработчик сообщений с интеграцией сессий и кеширования
"""
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, User
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Dict, Any, Optional
from enum import Enum
from core.interfaces import EventHandlerInterface
from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from services.payment_service import PaymentService
from services.balance_service import BalanceService
from services.star_purchase_service import StarPurchaseService
from services.session_cache import SessionCache
from services.rate_limit_cache import RateLimitCache
from services.payment_cache import PaymentCache


class PurchaseErrorType(Enum):
    """Типы ошибок при покупке"""
    INSUFFICIENT_BALANCE = "insufficient_balance"
    NETWORK_ERROR = "network_error"
    PAYMENT_SYSTEM_ERROR = "payment_system_error"
    VALIDATION_ERROR = "validation_error"
    SYSTEM_ERROR = "system_error"
    UNKNOWN_ERROR = "unknown_error"
    TRANSACTION_FAILED = "transaction_failed"


class PurchaseErrorHandler:
    """Универсальный обработчик ошибок покупок"""
    
    @staticmethod
    def categorize_error(error_message: str) -> PurchaseErrorType:
        """Категоризация ошибки по типу с улучшенной точностью"""
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
    
    @staticmethod
    def get_error_message(error_type: PurchaseErrorType, context: Optional[dict] = None) -> str:
        """Получение user-friendly сообщения об ошибке с контекстом и рекомендациями"""
        context = context or {}
        
        # Получаем общие данные из контекста
        user_id = context.get('user_id', 'неизвестный')
        amount = context.get('amount', 0)
        payment_id = context.get('payment_id', 'неизвестен')
        error_detail = context.get('error', 'Неизвестная ошибка')
        
        messages = {
            PurchaseErrorType.INSUFFICIENT_BALANCE: (
                "❌ <b>Недостаточно средств для покупки!</b> ❌\n\n"
                f"💰 <b>Ваш баланс:</b> {context.get('current_balance', 0):.2f} TON\n"
                f"💸 <b>Требуется:</b> {context.get('required_amount', amount)} TON\n"
                f"📉 <b>Не хватает:</b> {context.get('missing_amount', max(0, amount - context.get('current_balance', 0))):.2f} TON\n\n"
                f"🔧 <i><b>Рекомендуемые действия:</b></i>\n"
                f"   💳 <i>Пополнить баланс через Heleket</i>\n"
                f"   ⭐ <i>Выбрать меньшее количество звезд</i>\n"
                f"   💰 <i>Использовать другой способ оплаты</i>\n\n"
                f"📱 <i>Идентификатор операции: {payment_id}</i>\n\n"
                f"💡 <i>Введите /start для возврата в меню</i>"
            ),
            PurchaseErrorType.NETWORK_ERROR: (
                "🌐 <b>Проблемы с сетевым подключением</b> 🌐\n\n"
                f"🔍 <i>Не удалось подключиться к серверу оплаты</i>\n"
                f"📝 <i>Ошибка: {error_detail}</i>\n"
                f"👤 <i>Пользователь: {user_id}</i>\n\n"
                f"🔄 <i><b>Рекомендуемые действия:</b></i>\n"
                f"   📡 <i>Проверьте интернет-соединение</i>\n"
                f"   🔄 <i>Попробуйте снова через 30 секунд</i>\n"
                f"   📱 <i>Переключитесь на другую сеть Wi-Fi/мобильные данные</i>\n\n"
                f"📞 <i>Если проблема сохраняется, обратитесь в поддержку</i>\n\n"
                f"💡 <i>Введите /start для возврата в меню</i>"
            ),
            PurchaseErrorType.PAYMENT_SYSTEM_ERROR: (
                "💳 <b>Ошибка платежной системы</b> 💳\n\n"
                f"🔍 <i>Проблема с обработкой платежа</i>\n"
                f"📝 <i>Ошибка: {error_detail}</i>\n"
                f"💰 <i>Сумма: {amount} TON</i>\n\n"
                f"🔄 <i><b>Рекомендуемые действия:</b></i>\n"
                f"   ⏰ <i>Попробуйте снова через 5 минут</i>\n"
                f"   💳 <i>Используйте другой способ оплаты</i>\n"
                f"   💱 <i>Попробуйте другую валюту или карту</i>\n\n"
                f"📞 <i>Если проблема сохраняется, обратитесь в поддержку с ID: {payment_id}</i>\n\n"
                f"💡 <i>Введите /start для возврата в меню</i>"
            ),
            PurchaseErrorType.VALIDATION_ERROR: (
                "⚠️ <b>Ошибка валидации данных</b> ⚠️\n\n"
                f"🔍 <i>Некорректные данные для покупки</i>\n"
                f"📝 <i>Ошибка: {error_detail}</i>\n"
                f"🔢 <i>Введенное значение: {amount}</i>\n\n"
                f"🔄 <i><b>Рекомендуемые действия:</b></i>\n"
                f"   ✅ <i>Проверьте введенные данные</i>\n"
                f"   📏 <i>Убедитесь, что сумма находится в допустимом диапазоне</i>\n"
                f"   🔢 <i>Введите корректное числовое значение</i>\n\n"
                f"📱 <i>Для покупки звезд: от 1 до 10000</i>\n"
                f"💰 <i>Для пополнения: от 10 до 10000 TON</i>\n\n"
                f"💡 <i>Введите /start для возврата в меню</i>"
            ),
            PurchaseErrorType.TRANSACTION_FAILED: (
                "🔄 <b>Ошибка транзакции</b> 🔄\n\n"
                f"🔍 <i>Не удалось завершить транзакцию</i>\n"
                f"📝 <i>Ошибка: {error_detail}</i>\n"
                f"💰 <i>Сумма: {amount} TON</i>\n"
                f"🔢 <i>ID транзакции: {payment_id}</i>\n\n"
                f"🔄 <i><b>Рекомендуемые действия:</b></i>\n"
                f"   🔄 <i>Попробуйте снова</i>\n"
                f"   💳 <i>Проверьте баланс карты/кошелька</i>\n"
                f"   📱 <i>Убедитесь, что платеж разрешен банком</i>\n\n"
                f"📞 <i>Если проблема сохраняется, обратитесь в поддержку</i>\n\n"
                f"💡 <i>Введите /start для возврата в меню</i>"
            ),
            PurchaseErrorType.SYSTEM_ERROR: (
                "⚠️ <b>Системная ошибка</b> ⚠️\n\n"
                f"🔍 <i>Произошла внутренняя ошибка системы</i>\n"
                f"📝 <i>Ошибка: {error_detail}</i>\n"
                f"👤 <i>Пользователь: {user_id}</i>\n\n"
                f"🔄 <i><b>Рекомендуемые действия:</b></i>\n"
                f"   ⏰ <i>Попробуйте снова позже</i>\n"
                f"   🔄 <i>Обновите приложение или страницу</i>\n"
                f"   📱 <i>Очистите кеш браузера</i>\n\n"
                f"📞 <i>Если проблема сохраняется, обратитесь в поддержку</i>\n\n"
                f"💡 <i>Введите /start для возврата в меню</i>"
            ),
            PurchaseErrorType.UNKNOWN_ERROR: (
                "❓ <b>Неизвестная ошибка</b> ❓\n\n"
                f"🔍 <i>Произошла непредвиденная ошибка</i>\n"
                f"📝 <i>Ошибка: {error_detail}</i>\n"
                f"👤 <i>Пользователь: {user_id}</i>\n"
                f"💰 <i>Сумма: {amount} TON</i>\n\n"
                f"🔄 <i><b>Рекомендуемые действия:</b></i>\n"
                f"   🔄 <i>Попробуйте снова</i>\n"
                f"   📱 <i>Перезапустите приложение</i>\n"
                f"   🔄 <i>Обновите страницу</i>\n\n"
                f"📞 <i>Если проблема сохраняется, обратитесь в поддержку</i>\n\n"
                f"💡 <i>Введите /start для возврата в меню</i>"
            )
        }
        
        return messages.get(error_type, messages[PurchaseErrorType.UNKNOWN_ERROR])
    
    @staticmethod
    def get_suggested_actions(error_type: PurchaseErrorType) -> list:
        """Получение детализированных рекомендованных действий в зависимости от типа ошибки"""
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


class MessageHandler(EventHandlerInterface):
    """Обработчик сообщений с поддержкой сессий и кеширования"""

    def __init__(self,
                 user_repository: UserRepository,
                 payment_service: PaymentService,
                 balance_service: BalanceService,
                 star_purchase_service: StarPurchaseService,
                 session_cache: Optional[SessionCache] = None,
                 rate_limit_cache: Optional[RateLimitCache] = None,
                 payment_cache: Optional[PaymentCache] = None):
        self.user_repository = user_repository
        self.payment_service = payment_service
        self.balance_service = balance_service
        self.star_purchase_service = star_purchase_service
        self.session_cache = session_cache
        self.rate_limit_cache = rate_limit_cache
        self.payment_cache = payment_cache
        self.logger = logging.getLogger(__name__)

    async def _handle_purchase_error(self, error: Exception, context: Optional[dict] = None) -> PurchaseErrorType:
        """Обработка ошибок покупок с категоризацией и улучшенным логированием"""
        error_message = str(error)
        error_type = PurchaseErrorHandler.categorize_error(error_message)
        
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

    def _determine_previous_menu(self, callback_data: str) -> str:
        """Определение предыдущего меню на основе callback_data"""
        if callback_data.startswith(("buy_", "custom_")):
            return "Магазин звезд"
        elif callback_data.startswith(("recharge_", "check_recharge_")):
            return "Пополнение баланса"
        elif callback_data.startswith(("check_payment_", "payment_")):
            return "Проверка оплаты"
        elif callback_data in ["balance", "balance_history"]:
            return "Баланс"
        elif callback_data in ["help", "create_ticket"]:
            return "Помощь"
        else:
            return "Главное меню"

    async def _show_error_with_suggestions(self, message: Message | CallbackQuery, error_type: PurchaseErrorType, context: Optional[dict] = None) -> None:
        """Показ ошибки с рекомендациями действий и улучшенной навигацией"""
        error_message = PurchaseErrorHandler.get_error_message(error_type, context)
        suggested_actions = PurchaseErrorHandler.get_suggested_actions(error_type)
        
        # Создаем клавиатуру с рекомендованными действиями
        builder = InlineKeyboardBuilder()
        
        # Добавляем кнопки с рекомендованными действиями
        for action_text, action_callback in suggested_actions[:3]:  # Максимум 3 кнопки
            builder.row(InlineKeyboardButton(text=f"🔧 {action_text}", callback_data=f"error_action_{action_callback}"))
        
        # Кнопка возврата в логическое меню
        if isinstance(message, CallbackQuery):
            # Определяем, какое меню было до ошибки
            previous_menu = self._determine_previous_menu(message.data)
            builder.row(InlineKeyboardButton(text=f"⬅️ {previous_menu}", callback_data=f"back_to_{previous_menu.lower().replace(' ', '_')}"))
        else:
            builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_main"))
        
        # Кнопка помощи
        builder.row(InlineKeyboardButton(text="❓ Помощь", callback_data="help"))
        
        # Определяем, как отправить сообщение
        if isinstance(message, Message):
            await message.answer(error_message, reply_markup=builder.as_markup(), parse_mode="HTML")
        elif isinstance(message, CallbackQuery) and message.message:
            try:
                await message.message.edit_text(error_message, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                self.logger.error(f"Error editing message for error: {e}")
                await message.message.answer(error_message, reply_markup=builder.as_markup(), parse_mode="HTML")

    async def handle_message(self, message: Message, bot: Bot) -> None:
        """Обработка текстового сообщения с управлением сессиями"""
        if not message.from_user or not message.from_user.id:
            return

        user_id = message.from_user.id

        # Проверка rate limit
        if self.rate_limit_cache:
            allowed = await self.rate_limit_cache.check_user_rate_limit(
                user_id, "message", 10, 60
            )
            if not allowed:
                await message.answer("❌ Превышен лимит сообщений. Попробуйте позже.")
                return

        # Управление сессией
        if self.session_cache:
            # Получаем активные сессии пользователя
            user_sessions = await self.session_cache.get_user_sessions(user_id)
            if user_sessions:
                # Используем первую активную сессию
                session_data = user_sessions[0]
                await self._handle_message_with_session(message, bot, session_data)
            else:
                await self._create_new_session(message, bot)
        else:
            await self._handle_message_without_session(message, bot)

    async def handle_callback(self, callback: CallbackQuery, bot: Bot) -> None:
        """Обработка callback запросов с управлением сессиями"""
        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id

        # Проверка rate limit
        if self.rate_limit_cache:
            allowed = await self.rate_limit_cache.check_user_rate_limit(
                user_id, "callback", 20, 60
            )
            if not allowed:
                await callback.answer("❌ Превышен лимит запросов. Попробуйте позже.")
                return

        callback_data = callback.data

        # Обработка callback с учетом сессии
        if callback_data == "balance":
            await self._show_balance(callback, bot)
        elif callback_data == "recharge":
            await self._handle_recharge(callback, bot)
        elif callback_data == "back_to_main":
            await self._back_to_main(callback, bot)
        elif callback_data == "back_to_balance":
            await self._back_to_balance(callback, bot)
        elif callback_data == "recharge_heleket":
            await self._handle_recharge(callback, bot)
        elif callback_data == "recharge_custom":
            await self._show_recharge_custom_amount(callback, bot)
        elif callback_data == "recharge_10":
            await self._handle_recharge_amount(callback, bot, 10.0)
        elif callback_data == "recharge_50":
            await self._handle_recharge_amount(callback, bot, 50.0)
        elif callback_data == "recharge_100":
            await self._handle_recharge_amount(callback, bot, 100.0)
        elif callback_data == "recharge_500":
            await self._handle_recharge_amount(callback, bot, 500.0)
        elif callback_data == "recharge_custom_amount":
            if callback.message:
                try:
                    await callback.message.edit_text("Введите сумму для пополнения (от 10 до 10000 TON):")
                except Exception as e:
                    self.logger.error(f"Error editing message for recharge_custom_amount: {e}")
                    await callback.message.answer("Введите сумму для пополнения (от 10 до 10000 TON):")
        elif callback_data.startswith("check_recharge_"):
            await self._check_recharge_status(callback, bot)
        elif callback_data == "buy_stars":
            await self._show_buy_stars(callback, bot)
        elif callback_data == "buy_stars_with_balance":
            await self._show_buy_stars_with_balance(callback, bot)
        elif callback_data == "custom_amount":
            await self._show_custom_amount(callback, bot)
        elif callback_data == "custom_amount_balance":
            await self._show_custom_amount_balance(callback, bot)
        elif callback_data == "back_to_buy_stars":
            await self._back_to_buy_stars(callback, bot)
        elif callback_data == "buy_100":
            await self._buy_stars_100(callback, bot)
        elif callback_data == "buy_250":
            await self._buy_stars_250(callback, bot)
        elif callback_data == "buy_500":
            await self._buy_stars_500(callback, bot)
        elif callback_data == "buy_1000":
            await self._buy_stars_1000(callback, bot)
        elif callback_data == "buy_100_balance":
            await self._buy_stars_100_balance(callback, bot)
        elif callback_data == "buy_250_balance":
            await self._buy_stars_250_balance(callback, bot)
        elif callback_data == "buy_500_balance":
            await self._buy_stars_500_balance(callback, bot)
        elif callback_data == "buy_1000_balance":
            await self._buy_stars_1000_balance(callback, bot)
        elif callback_data == "help":
            await self._show_help(callback, bot)
        elif callback_data == "create_ticket":
            await self._create_ticket(callback, bot)
        elif callback_data == "back_to_help":
            await self._back_to_help(callback, bot)
        elif callback_data == "balance_history":
            await self._show_balance_history(callback, bot)
        elif callback_data.startswith("check_payment_"):
            await self._check_payment_status(callback, bot)
        elif callback_data.startswith("error_action_"):
            await self._handle_error_action(callback, bot)
        elif callback_data.startswith("back_to_"):
            await self._handle_back_to_menu(callback, bot)

    def register_handlers(self, dp: Dispatcher) -> None:
        """Регистрация обработчиков"""
        # Обработка команды /start
        dp.message.register(self.cmd_start, Command("start"))

        # Обработка текстовых сообщений
        dp.message.register(self.handle_message)

        # Обработка callback
        dp.callback_query.register(self.handle_callback)

    async def cmd_start(self, message: Message, bot: Bot) -> None:
        """Обработка команды /start с созданием сессии и улучшенной валидацией"""
        if not message.from_user or not message.from_user.id:
            return

        user_id = message.from_user.id

        # Добавление пользователя в базу данных
        await self.user_repository.add_user(user_id)

        # Создание сессии
        if self.session_cache:
            await self.session_cache.create_session(user_id, {"state": "main"})

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
            InlineKeyboardButton(text="⭐ Покупка Звезд", callback_data="buy_stars")
        )
        builder.row(
            InlineKeyboardButton(text="❓ Помощь", callback_data="help")
        )

        welcome_message = (
            "🌟 <b>MirzaShopBot</b> 🌟\n\n"
            "✨ Ваш личный магазин звезд! ✨\n\n"
            "🎯 <i>Добро пожаловать в мир уникальных возможностей!</i>\n\n"
            "🔹 <b>Основные функции:</b>\n"
            "   💳 Управление балансом\n"
            "   ⭐ Покупка звезд\n"
            "   🎁 Бонусы и акции\n"
            "   📊 История транзакций\n\n"
            "🚀 <i>Выберите действие ниже, чтобы начать!</i>\n\n"
            "🌟 <b>Ваши звезды ждут вас!</b> 🌟"
        )

        await message.answer(
            welcome_message,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

        # Проверяем, является ли сообщение числом для покупки звезд с баланса
        if message.text and message.text.isdigit():
            amount = int(message.text)
            if 1 <= amount <= 10000:
                await self._create_star_purchase_custom_balance(message, bot, amount)
            else:
                await message.answer("❌ Пожалуйста, введите количество звезд от 1 до 10000")
        elif message.text:
            input_text = message.text.strip()
            
            # Проверяем, является ли сообщение числом для пополнения баланса
            if all(c.isdigit() or c == '.' for c in input_text):
                if input_text.count('.') <= 1:  # Только одна точка
                    try:
                        amount = float(input_text)
                        if amount > 0 and 10 <= amount <= 10000:
                            await self._handle_recharge_custom_amount_input(message, bot)
                        elif amount <= 0:
                            await message.answer("❌ Сумма должна быть больше 0 TON")
                        elif amount < 10:
                            await message.answer("❌ Минимальная сумма для пополнения - 10 TON")
                        elif amount > 10000:
                            await message.answer("❌ Максимальная сумма для пополнения - 10000 TON")
                        else:
                            await message.answer("❌ Пожалуйста, введите корректную сумму для пополнения")
                    except ValueError:
                        await message.answer("❌ Пожалуйста, введите корректную сумму числом")
                else:
                    await message.answer("❌ Пожалуйста, введите корректную сумму (только одна точка)")

    async def _handle_message_with_session(self, message: Message, bot: Bot, session_data: dict) -> None:
        """Обработка сообщения с сохранением состояния сессии и улучшенной валидацией"""
        # Проверяем, является ли сообщение числом для покупки звезд
        if message.text and message.text.isdigit():
            amount = int(message.text)
            if 1 <= amount <= 10000:
                await self._create_star_purchase_custom(message, bot, amount)
            else:
                await message.answer("❌ Пожалуйста, введите количество звезд от 1 до 10000")
        else:
            # Проверяем, является ли сообщение числом для пополнения баланса
            if message.text:
                input_text = message.text.strip()
                
                # Улучшенная валидация для пополнения баланса
                if all(c.isdigit() or c == '.' for c in input_text):
                    if input_text.count('.') <= 1:  # Только одна точка
                        try:
                            amount = float(input_text)
                            if amount > 0 and 10 <= amount <= 10000:
                                await self._handle_recharge_custom_amount_input(message, bot)
                            elif amount <= 0:
                                await message.answer("❌ Сумма должна быть больше 0 TON")
                            elif amount < 10:
                                await message.answer("❌ Минимальная сумма для пополнения - 10 TON")
                            elif amount > 10000:
                                await message.answer("❌ Максимальная сумма для пополнения - 10000 TON")
                            else:
                                await message.answer("❌ Пожалуйста, введите корректную сумму для пополнения")
                        except ValueError:
                            await message.answer("❌ Пожалуйста, введите корректную сумму числом")
                    else:
                        await message.answer("❌ Пожалуйста, введите корректную сумму (только одна точка)")
                else:
                    await message.answer("✅ Ваше сообщение получено. Спасибо за использование бота!")
            else:
                await message.answer("✅ Ваше сообщение получено. Спасибо за использование бота!")

    async def _create_new_session(self, message: Message, bot: Bot) -> None:
        """Создание новой сессии пользователя с улучшенной валидацией"""
        if not message.from_user or not message.from_user.id:
            return

        session_data = {
            "user_id": message.from_user.id,
            "state": "main",
            "created_at": message.date.isoformat() if message.date else None
        }

        if self.session_cache:
            await self.session_cache.create_session(message.from_user.id, session_data)

        await message.answer("✅ Новая сессия создана. Спасибо за использование бота!")

        # Проверяем, является ли сообщение числом для покупки звезд с баланса
        if message.text and message.text.isdigit():
            amount = int(message.text)
            if 1 <= amount <= 10000:
                await self._create_star_purchase_custom_balance(message, bot, amount)
            else:
                await message.answer("❌ Пожалуйста, введите количество звезд от 1 до 10000")
        elif message.text:
            input_text = message.text.strip()
            
            # Проверяем, является ли сообщение числом для пополнения баланса
            if all(c.isdigit() or c == '.' for c in input_text):
                if input_text.count('.') <= 1:  # Только одна точка
                    try:
                        amount = float(input_text)
                        if amount > 0 and 10 <= amount <= 10000:
                            await self._handle_recharge_custom_amount_input(message, bot)
                        elif amount <= 0:
                            await message.answer("❌ Сумма должна быть больше 0 TON")
                        elif amount < 10:
                            await message.answer("❌ Минимальная сумма для пополнения - 10 TON")
                        elif amount > 10000:
                            await message.answer("❌ Максимальная сумма для пополнения - 10000 TON")
                        else:
                            await message.answer("❌ Пожалуйста, введите корректную сумму для пополнения")
                    except ValueError:
                        await message.answer("❌ Пожалуйста, введите корректную сумму числом")
                else:
                    await message.answer("❌ Пожалуйста, введите корректную сумму (только одна точка)")
            else:
                await message.answer("✅ Новая сессия создана. Ваше сообщение получено. Спасибо за использование бота!")
        else:
            await message.answer("✅ Новая сессия создана. Спасибо за использование бота!")

        if self.session_cache:
            await self.session_cache.create_session(message.from_user.id, session_data)

        await message.answer("✅ Новая сессия создана. Спасибо за использование бота!")

    async def _handle_message_without_session(self, message: Message, bot: Bot) -> None:
        """Обработка сообщения без сессий с улучшенной валидацией"""
        # Проверяем, является ли сообщение числом для покупки звезд
        if message.text and message.text.isdigit():
            amount = int(message.text)
            if 1 <= amount <= 10000:
                await self._create_star_purchase_custom(message, bot, amount)
            else:
                await message.answer("❌ Пожалуйста, введите количество звезд от 1 до 10000")
        else:
            # Проверяем, является ли сообщение числом для пополнения баланса
            if message.text:
                input_text = message.text.strip()
                
                # Улучшенная валидация для пополнения баланса
                if all(c.isdigit() or c == '.' for c in input_text):
                    if input_text.count('.') <= 1:  # Только одна точка
                        try:
                            amount = float(input_text)
                            if amount > 0 and 10 <= amount <= 10000:
                                await self._handle_recharge_custom_amount_input(message, bot)
                            elif amount <= 0:
                                await message.answer("❌ Сумма должна быть больше 0 TON")
                            elif amount < 10:
                                await message.answer("❌ Минимальная сумма для пополнения - 10 TON")
                            elif amount > 10000:
                                await message.answer("❌ Максимальная сумма для пополнения - 10000 TON")
                            else:
                                await message.answer("❌ Пожалуйста, введите корректную сумму для пополнения")
                        except ValueError:
                            await message.answer("❌ Пожалуйста, введите корректную сумму числом")
                    else:
                        await message.answer("❌ Пожалуйста, введите корректную сумму (только одна точка)")
                else:
                    await message.answer("✅ Ваше сообщение получено. Спасибо за использование бота!")
            else:
                await message.answer("✅ Ваше сообщение получено. Спасибо за использование бота!")

    async def _show_balance(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение баланса пользователя"""
        await callback.answer()

        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id

        try:
            # Получаем баланс через новый сервис
            balance_data = await self.balance_service.get_user_balance(user_id)

            if balance_data:
                balance = balance_data.get("balance", 0)
                currency = balance_data.get("currency", "TON")
                source = balance_data.get("source", "unknown")

                builder = InlineKeyboardBuilder()
                builder.row(
                    InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="recharge"),
                    InlineKeyboardButton(text="📊 История транзакций", callback_data="balance_history")
                )
                builder.row(
                    InlineKeyboardButton(text="⬅️ Вернуться в меню", callback_data="back_to_main")
                )

                balance_message = (
                    f"💰 <b>Ваш баланс</b> 💰\n\n"
                    f"⭐ <b>{balance:.2f} {currency}</b>\n"
                    f"📊 <i>Источник: {source}</i>\n\n"
                    f"🎯 <i>Используйте звезды для различных функций внутри бота!</i>\n\n"
                    f"✨ <i>Доступные действия:</i>\n"
                    f"   • Покупка дополнительных звезд\n"
                    f"   • Доступ к премиум-функциям\n"
                    f"   • Улучшение пользовательского опыта\n\n"
                    f"💎 <i>Каждая звезда имеет ценность!</i>"
                )

                if callback.message:
                    try:
                        await callback.message.edit_text(
                            balance_message,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        self.logger.error(f"Error editing message in _show_balance: {e}")
                        await callback.message.answer(
                            balance_message,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
            else:
                # Если не удалось получить баланс, показываем ошибку
                builder = InlineKeyboardBuilder()
                builder.row(
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
                )

                if callback.message:
                    try:
                        await callback.message.edit_text(
                            "❌ <b>Не удалось получить баланс</b> ❌\n\n"
                            f"🔧 <i>Пожалуйста, попробуйте позже</i>\n\n"
                            f"💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        self.logger.error(f"Error editing message in _show_balance error case: {e}")
                        await callback.message.answer(
                            "❌ <b>Не удалось получить баланс</b> ❌\n\n"
                            f"🔧 <i>Пожалуйста, попробуйте позже</i>\n\n"
                            f"💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )

        except Exception as e:
            self.logger.error(f"Error showing balance for user {user_id}: {e}")

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
            )

            if callback.message:
                try:
                    await callback.message.edit_text(
                        "❌ <b>Произошла ошибка при получении баланса</b> ❌\n\n"
                        f"🔧 <i>Попробуйте обновить страницу</i>\n\n"
                        f"💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Error editing message in _show_balance exception case: {e}")
                    await callback.message.answer(
                        "❌ <b>Произошла ошибка при получении баланса</b> ❌\n\n"
                        f"🔧 <i>Попробуйте обновить страницу</i>\n\n"
                        f"💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )

    async def _handle_recharge(self, callback: CallbackQuery, bot: Bot) -> None:
        """Обработка выбора способа пополнения"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="💳 Пополнить через Heleket", callback_data="recharge_heleket"),
            InlineKeyboardButton(text="💎 Быстрое пополнение", callback_data="recharge_custom"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_balance")
        )

        if callback.message:
            try:
                await callback.message.edit_text(
                    "Выберите способ пополнения:",
                    reply_markup=builder.as_markup()
                )
            except Exception as e:
                self.logger.error(f"Error editing message in _handle_recharge: {e}")
                await callback.message.answer(
                    "Выберите способ пополнения:",
                    reply_markup=builder.as_markup()
                )

    async def _back_to_main(self, callback: CallbackQuery, bot: Bot) -> None:
        """Возврат в главное меню"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
            InlineKeyboardButton(text="⭐ Покупка Звезд", callback_data="buy_stars")
        )
        builder.row(
            InlineKeyboardButton(text="❓ Помощь", callback_data="help")
        )

        welcome_message = (
            "🌟 <b>MirzaShopBot</b> 🌟\n\n"
            "✨ Ваш личный магазин звезд! ✨\n\n"
            "🎯 <i>Добро пожаловать в мир уникальных возможностей!</i>\n\n"
            "🔹 <b>Основные функции:</b>\n"
            "   💳 Управление балансом\n"
            "   ⭐ Покупка звезд\n"
            "   🎁 Бонусы и акции\n"
            "   📊 История транзакций\n\n"
            "🚀 <i>Выберите действие ниже, чтобы начать!</i>\n\n"
            "🌟 <b>Ваши звезды ждут вас!</b> 🌟"
        )

        if callback.message:
            try:
                await callback.message.edit_text(
                    welcome_message,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
            except Exception as e:
                self.logger.error(f"Error editing message in _back_to_main: {e}")
                await callback.message.answer(
                    welcome_message,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )

    async def _back_to_balance(self, callback: CallbackQuery, bot: Bot) -> None:
        """Возврат к экрану баланса"""
        await callback.answer()
        await self._show_balance(callback, bot)

    async def _show_buy_stars(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение экрана покупки звезд"""
        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⭐ 100 звезд 💎", callback_data="buy_100"),
            InlineKeyboardButton(text="⭐ 250 звезд 💎", callback_data="buy_250")
        )
        builder.row(
            InlineKeyboardButton(text="⭐ 500 звезд 💎", callback_data="buy_500"),
            InlineKeyboardButton(text="⭐ 1000 звезд 💎", callback_data="buy_1000")
        )
        builder.row(
            InlineKeyboardButton(text="💰 Купить с баланса", callback_data="buy_stars_with_balance"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
        )

        stars_message = (
            "⭐ <b>Магазин звезд</b> ⭐\n\n"
            "🌟 <i>Выберите идеальный пакет для ваших нужд!</i> 🌟\n\n"
            "💎 <b>Каждая звезда открывает новые возможности</b> 💎\n\n"
            "🎯 <b>Доступные пакеты:</b>\n\n"
            "🔸 <b>100 звезд</b> - <i>Идеально для начала</i>\n"
            "   🎁 <i>+10 бонусных звезд</i>\n"
            "   💰 <i>Экономия: 5%</i>\n\n"
            "🔸 <b>250 звезд</b> - <i>Популярный выбор</i>\n"
            "   🎁 <i>+25 бонусных звезд</i>\n"
            "   💰 <i>Экономия: 10%</i>\n\n"
            "🔸 <b>500 звезд</b> - <i>Оптимальное решение</i>\n"
            "   🎁 <i>+50 бонусных звезд</i>\n"
            "   💰 <i>Экономия: 15%</i>\n\n"
            "🔸 <b>1000 звезд</b> - <i>Максимальная выгода</i>\n"
            "   🎁 <i>+100 бонусных звезд</i>\n"
            "   💰 <i>Экономия: 20%</i>\n\n"
            "🚀 <i>Чем больше пакет, тем выше бонус!</i>"
        )

        if callback.message:
            try:
                await callback.message.edit_text(
                    stars_message,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
            except Exception as e:
                self.logger.error(f"Error editing message in _show_buy_stars: {e}")
                await callback.message.answer(
                    stars_message,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )

    async def _show_buy_stars_with_balance(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение экрана покупки звезд с баланса"""
        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id
        await callback.answer()

        # Получаем баланс пользователя
        balance_data = await self.balance_service.get_user_balance(user_id)
        balance = balance_data.get("balance", 0) if balance_data else 0

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text=f"⭐ 100 звезд 💎 ({100} TON)", callback_data="buy_100_balance"),
            InlineKeyboardButton(text=f"⭐ 250 звезд 💎 ({250} TON)", callback_data="buy_250_balance")
        )
        builder.row(
            InlineKeyboardButton(text=f"⭐ 500 звезд 💎 ({500} TON)", callback_data="buy_500_balance"),
            InlineKeyboardButton(text=f"⭐ 1000 звезд 💎 ({1000} TON)", callback_data="buy_1000_balance")
        )
        builder.row(
            InlineKeyboardButton(text="🎯 Своя сумма", callback_data="custom_amount_balance"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
        )

        balance_stars_message = (
            f"💰 <b>Ваш баланс</b>: {balance:.2f} TON\n\n"
            "⭐ <b>Покупка звезд с баланса</b> ⭐\n\n"
            "🎯 <i>Выберите пакет или введите свою сумму</i> 🎯\n\n"
            "💎 <b>Быстрая покупка без комиссий</b> 💎\n\n"
            "✨ <b>Преимущества:</b>\n"
            "   ⚡ <i>Мгновенная покупка</i>\n"
            "   💰 <i>Без дополнительных комиссий</i>\n"
            "   🎁 <i>Удобный способ пополнения</i>\n\n"
            "🔥 <i>Используйте свой баланс для быстрой и удобной покупки!</i>"
        )

        if callback.message:
            try:
                await callback.message.edit_text(
                    balance_stars_message,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
            except Exception as e:
                self.logger.error(f"Error editing message in _show_buy_stars_with_balance: {e}")
                await callback.message.answer(
                    balance_stars_message,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )

    async def _buy_stars_100_balance(self, callback: CallbackQuery, bot: Bot) -> None:
        """Покупка 100 звезд с баланса"""
        await callback.answer()
        await self._create_star_purchase_balance(callback, bot, 100)

    async def _buy_stars_250_balance(self, callback: CallbackQuery, bot: Bot) -> None:
        """Покупка 250 звезд с баланса"""
        await callback.answer()
        await self._create_star_purchase_balance(callback, bot, 250)

    async def _buy_stars_500_balance(self, callback: CallbackQuery, bot: Bot) -> None:
        """Покупка 500 звезд с баланса"""
        await callback.answer()
        await self._create_star_purchase_balance(callback, bot, 500)

    async def _buy_stars_1000_balance(self, callback: CallbackQuery, bot: Bot) -> None:
        """Покупка 1000 звезд с баланса"""
        await callback.answer()
        await self._create_star_purchase_balance(callback, bot, 1000)

    async def _create_star_purchase_balance(self, callback: CallbackQuery, bot: Bot, amount: int) -> None:
        """Создание покупки звезд с баланса пользователя"""
        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id

        try:
            # Сохраняем текущее состояние для восстановления в случае ошибки
            original_message = callback.message
            original_callback_data = callback.data

            # Используем новый сервис покупки звезд с баланса
            purchase_result = await self.star_purchase_service.create_star_purchase(
                user_id=user_id,
                amount=amount,
                purchase_type="balance"
            )

            if purchase_result["status"] == "failed":
                error_msg = purchase_result.get("error", "Неизвестная ошибка")
                
                # Используем универсальный обработчик ошибок
                error_type = await self._handle_purchase_error(Exception(error_msg), {"user_id": user_id, "amount": amount})
                
                # Получаем баланс для контекста
                balance_data = await self.balance_service.get_user_balance(user_id)
                balance = balance_data.get("balance", 0) if balance_data else 0
                
                # Формируем контекст для сообщения об ошибке
                error_context = {
                    "current_balance": balance,
                    "required_amount": amount,
                    "missing_amount": max(0, amount - balance),
                    "user_id": user_id,
                    "amount": amount
                }
                
                # Показываем ошибку с рекомендациями
                await self._show_error_with_suggestions(callback, error_type, error_context)
                return

            # Показываем успешное сообщение
            old_balance = purchase_result.get("old_balance", 0)
            new_balance = purchase_result.get("new_balance", 0)
            stars_count = purchase_result.get("stars_count", 0)

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="📊 История покупок", callback_data="purchase_history"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
            )

            success_message = (
                f"🎉 <b>Покупка успешна!</b> 🎉\n\n"
                f"⭐ <b>Куплено звезд:</b> {stars_count}\n"
                f"💰 <b>Баланс до:</b> {old_balance:.2f} TON\n"
                f"💰 <b>Баланс после:</b> {new_balance:.2f} TON\n\n"
                f"🌟 <i>Спасибо за покупку!</i> 🌟\n\n"
                f"✨ Ваши звезды уже доступны для использования!"
            )

            if callback.message:
                try:
                    await callback.message.edit_text(
                        success_message,
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Error editing message in _create_star_purchase_balance success case: {e}")
                    await callback.message.answer(
                        success_message,
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )

        except Exception as e:
            self.logger.error(f"Error creating star purchase with balance for user {user_id}: {e}")

            # Используем универсальный обработчик ошибок
            error_type = await self._handle_purchase_error(e, {"user_id": user_id, "amount": amount})
            
            # Показываем ошибку с рекомендациями
            await self._show_error_with_suggestions(callback, error_type, {"user_id": user_id, "amount": amount, "error": str(e)})

    async def _show_buy_stars_with_error(self, callback: CallbackQuery, bot: Bot, error_message: str, failed_amount: Optional[int] = None) -> None:
        """Отображение меню покупок с сообщением об ошибке"""
        await callback.answer()

        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id

        # Получаем баланс пользователя для отображения в меню
        balance_data = await self.balance_service.get_user_balance(user_id)
        balance = balance_data.get("balance", 0) if balance_data else 0

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text=f"⭐ 100 звезд 💎 ({100} TON)", callback_data="buy_100_balance"),
            InlineKeyboardButton(text=f"⭐ 250 звезд 💎 ({250} TON)", callback_data="buy_250_balance")
        )
        builder.row(
            InlineKeyboardButton(text=f"⭐ 500 звезд 💎 ({500} TON)", callback_data="buy_500_balance"),
            InlineKeyboardButton(text=f"⭐ 1000 звезд 💎 ({1000} TON)", callback_data="buy_1000_balance")
        )
        builder.row(
            InlineKeyboardButton(text="🎯 Своя сумма", callback_data="custom_amount_balance"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
        )

        # Формируем сообщение с ошибкой и балансом
        balance_stars_message = (
            f"💰 <b>Ваш баланс</b>: {balance:.2f} TON\n\n"
            f"{error_message}\n\n"
            "⭐ <b>Покупка звезд с баланса</b> ⭐\n\n"
            "🎯 <i>Выберите пакет или введите свою сумму</i> 🎯\n\n"
            "💎 <b>Быстрая покупка без комиссий</b> 💎\n\n"
            "✨ <b>Преимущества:</b>\n"
            "   ⚡ <i>Мгновенная покупка</i>\n"
            "   💰 <i>Без дополнительных комиссий</i>\n"
            "   🎁 <i>Удобный способ пополнения</i>\n\n"
            "🔥 <i>Используйте свой баланс для быстрой и удобной покупки!</i>"
        )

        if callback.message:
            try:
                await callback.message.edit_text(
                    balance_stars_message,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
            except Exception as e:
                self.logger.error(f"Error editing message in _show_buy_stars_with_error: {e}")
                await callback.message.answer(
                    balance_stars_message,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )

    async def _show_custom_amount_balance(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение экрана ввода своей суммы для покупки с баланса"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
        )

        if callback.message:
            try:
                await callback.message.edit_text(
                    "🎯 <b>Введите сумму звезд для покупки с баланса</b> 🎯\n\n"
                    f"💡 <i>Введите количество звезд от 1 до 10000</i>\n\n"
                    f"🔧 <i>Сумма будет списана с вашего баланса</i>\n\n"
                    f"💰 <i>Убедитесь, что на баланке достаточно средств</i>",
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
            except Exception as e:
                self.logger.error(f"Error editing message in _show_custom_amount_balance: {e}")
                await callback.message.answer(
                    "🎯 <b>Введите сумму звезд для покупки с баланса</b> 🎯\n\n"
                    f"💡 <i>Введите количество звезд от 1 до 10000</i>\n\n"
                    f"🔧 <i>Сумма будет списана с вашего баланса</i>\n\n"
                    f"💰 <i>Убедитесь, что на баланке достаточно средств</i>",
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )

    async def _create_star_purchase_custom_balance(self, message: Message, bot: Bot, amount: int) -> None:
        """Создание покупки звезд для пользовательской суммы с баланса"""
        if not message.from_user or not message.from_user.id:
            return

        user_id = message.from_user.id

        try:
            # Используем новый сервис покупки звезд с баланса
            purchase_result = await self.star_purchase_service.create_star_purchase(
                user_id=user_id,
                amount=amount,
                purchase_type="balance"
            )

            if purchase_result["status"] == "failed":
                error_msg = purchase_result.get("error", "Неизвестная ошибка")
                
                # Используем универсальный обработчик ошибок
                error_type = await self._handle_purchase_error(Exception(error_msg), {"user_id": user_id, "amount": amount})
                
                # Получаем баланс для контекста
                balance_data = await self.balance_service.get_user_balance(user_id)
                balance = balance_data.get("balance", 0) if balance_data else 0
                
                # Формируем контекст для сообщения об ошибке
                error_context = {
                    "current_balance": balance,
                    "required_amount": amount,
                    "missing_amount": max(0, amount - balance),
                    "user_id": user_id,
                    "amount": amount
                }
                
                # Показываем ошибку с рекомендациями
                await self._show_error_with_suggestions(message, error_type, error_context)
                return

            # Показываем успешное сообщение
            old_balance = purchase_result.get("old_balance", 0)
            new_balance = purchase_result.get("new_balance", 0)
            stars_count = purchase_result.get("stars_count", 0)

            success_message = (
                f"🎉 <b>Покупка успешна!</b> 🎉\n\n"
                f"⭐ <b>Куплено звезд:</b> {stars_count}\n"
                f"💰 <b>Баланс до:</b> {old_balance:.2f} TON\n"
                f"💰 <b>Баланс после:</b> {new_balance:.2f} TON\n\n"
                f"🌟 <i>Спасибо за покупку!</i> 🌟\n\n"
                f"✨ Ваши звезды уже доступны для использования!"
            )

            await message.answer(success_message, parse_mode="HTML")

        except Exception as e:
            self.logger.error(f"Error creating custom star purchase with balance for user {user_id}: {e}")
            
            # Используем универсальный обработчик ошибок
            error_type = await self._handle_purchase_error(e, {"user_id": user_id, "amount": amount})
            
            # Показываем ошибку с рекомендациями
            await self._show_error_with_suggestions(message, error_type, {"user_id": user_id, "amount": amount, "error": str(e)})

    async def _show_custom_amount(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение экрана ввода своей суммы"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
        )

        if callback.message:
            try:
                await callback.message.edit_text(
                    "Введите сумму звезд для покупки:",
                    reply_markup=builder.as_markup()
                )
            except Exception as e:
                self.logger.error(f"Error editing message in _show_custom_amount: {e}")
                await callback.message.answer(
                    "Введите сумму звезд для покупки:",
                    reply_markup=builder.as_markup()
                )

    async def _back_to_buy_stars(self, callback: CallbackQuery, bot: Bot) -> None:
        """Возврат к экрану покупки звезд"""
        await callback.answer()
        await self._show_buy_stars(callback, bot)

    async def _buy_stars_100(self, callback: CallbackQuery, bot: Bot) -> None:
        """Покупка 100 звезд"""
        await callback.answer()
        await self._create_star_purchase(callback, bot, 100)

    async def _buy_stars_250(self, callback: CallbackQuery, bot: Bot) -> None:
        """Покупка 250 звезд"""
        await callback.answer()
        await self._create_star_purchase(callback, bot, 250)

    async def _buy_stars_500(self, callback: CallbackQuery, bot: Bot) -> None:
        """Покупка 500 звезд"""
        await callback.answer()
        await self._create_star_purchase(callback, bot, 500)

    async def _buy_stars_1000(self, callback: CallbackQuery, bot: Bot) -> None:
        """Покупка 1000 звезд"""
        await callback.answer()
        await self._create_star_purchase(callback, bot, 1000)

    async def _create_star_purchase(self, callback: CallbackQuery, bot: Bot, amount: int) -> None:
        """Создание покупки звезд через Heleket"""
        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id

        try:
            # Используем новый сервис покупки звезд
            purchase_result = await self.star_purchase_service.create_star_purchase(user_id, amount)

            if purchase_result["status"] == "failed":
                error_msg = purchase_result.get("error", "Неизвестная ошибка")
                
                # Используем универсальный обработчик ошибок
                error_type = await self._handle_purchase_error(Exception(error_msg), {"user_id": user_id, "amount": amount})
                
                # Показываем ошибку с рекомендациями
                await self._show_error_with_suggestions(callback, error_type, {"user_id": user_id, "amount": amount})
                return

            result = purchase_result.get("result", {})
            transaction_id = purchase_result.get("transaction_id")

            if not result or "uuid" not in result or "url" not in result:
                if callback.message:
                    try:
                        await callback.message.edit_text("❌ Ошибка: некорректные данные от платежной системы")
                    except Exception as e:
                        self.logger.error(f"Error editing message in _create_star_purchase data error case: {e}")
                        await callback.message.answer("❌ Ошибка: некорректные данные от платежной системы")
                return

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text="🔍 Проверить оплату",
                    callback_data=f"check_payment_{result['uuid']}"
                )
            )
            builder.row(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_to_buy_stars"
                )
            )

            if callback.message:
                try:
                    await callback.message.edit_text(
                        f"✅ <b>Создан счет на покупку {amount} звезд</b> ✅\n\n"
                        f"💳 <b>Ссылка на оплату:</b> {result['url']}\n\n"
                        f"📋 <b>ID счета:</b> {result['uuid']}\n"
                        f"🔢 <b>ID транзакции:</b> {transaction_id}\n\n"
                        f"🔗 <i>Перейдите по ссылке для оплаты</i>\n"
                        f"⏰ <i>Счет действителен в течение 15 минут</i>",
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Error editing message in _create_star_purchase success case: {e}")
                    await callback.message.answer(
                        f"✅ Создан счет на покупку {amount} звезд.\n\n"
                        f"💳 Ссылка на оплату: {result['url']}\n\n"
                        f"📋 ID счета: {result['uuid']}\n"
                        f"🔢 ID транзакции: {transaction_id}",
                        reply_markup=builder.as_markup()
                    )

        except Exception as e:
            self.logger.error(f"Error creating star purchase for user {user_id}: {e}")
            
            # Используем универсальный обработчик ошибок
            error_type = await self._handle_purchase_error(e, {"user_id": user_id, "amount": amount})
            
            # Показываем ошибку с рекомендациями
            await self._show_error_with_suggestions(callback, error_type, {"user_id": user_id, "amount": amount, "error": str(e)})

    async def _create_star_purchase_custom(self, message: Message, bot: Bot, amount: int) -> None:
        """Создание покупки звезд для пользовательской суммы"""
        if not message.from_user or not message.from_user.id:
            return

        user_id = message.from_user.id

        try:
            # Используем новый сервис покупки звезд
            purchase_result = await self.star_purchase_service.create_star_purchase(user_id, amount)

            if purchase_result["status"] == "failed":
                error_msg = purchase_result.get("error", "Неизвестная ошибка")
                
                # Используем универсальный обработчик ошибок
                error_type = await self._handle_purchase_error(Exception(error_msg), {"user_id": user_id, "amount": amount})
                
                # Показываем ошибку с рекомендациями
                await self._show_error_with_suggestions(message, error_type, {"user_id": user_id, "amount": amount})
                return

            result = purchase_result.get("result", {})
            transaction_id = purchase_result.get("transaction_id")

            if not result or "uuid" not in result or "url" not in result:
                await message.answer("❌ Ошибка: некорректные данные от платежной системы")
                return

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text="🔍 Проверить оплату",
                    callback_data=f"check_payment_{result['uuid']}"
                )
            )
            builder.row(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_to_buy_stars"
                )
            )

            await message.answer(
                f"✅ Создан счет на покупку {amount} звезд.\n\n"
                f"💳 Ссылка на оплату: {result['url']}\n\n"
                f"📋 ID счета: {result['uuid']}\n"
                f"🔢 ID транзакции: {transaction_id}",
                reply_markup=builder.as_markup()
            )

        except Exception as e:
            self.logger.error(f"Error creating custom star purchase for user {user_id}: {e}")
            
            # Используем универсальный обработчик ошибок
            error_type = await self._handle_purchase_error(e, {"user_id": user_id, "amount": amount})
            
            # Показываем ошибку с рекомендациями
            await self._show_error_with_suggestions(message, error_type, {"user_id": user_id, "amount": amount, "error": str(e)})

    async def _show_help(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение экрана помощи"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🎫 Создать тикет", callback_data="create_ticket"),
            InlineKeyboardButton(text="📚 Частые вопросы", callback_data="faq"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
        )

        help_message = (
            "🤖 <b>Помощь и поддержка</b> 🤖\n\n"
            "🎯 <b>Основные возможности бота:</b>\n"
            "   💳 Управление балансом TON\n"
            "   ⭐ Покупка звезд через Heleket\n"
            "   🎁 Бонусы и специальные предложения\n"
            "   📊 История транзакций\n"
            "   🎫 Техническая поддержка\n\n"
            "💡 <b>Как начать:</b>\n"
            "   1. 🔍 Проверьте свой баланс\n"
            "   2. ⭐ Выберите пакет звезд\n"
            "   3. 💳 Оплатите удобным способом\n"
            "   4. 🎉 Наслаждайтесь использованием!\n\n"
            "🌟 <b>Звезды можно использовать:</b>\n"
            "   🔓 Доступ к премиум-функциям\n"
            "   ✨ Улучшение пользовательского опыта\n"
            "   🎁 Специальные предложения\n\n"
            "📞 <b>Контакты поддержки:</b>\n"
            "   📧 Напишите нам для быстрой помощи\n"
            "   🕒 Ответ в течение 24 часов"
        )

        if callback.message:
            await callback.message.answer(
                help_message,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )

    async def _create_ticket(self, callback: CallbackQuery, bot: Bot) -> None:
        """Создание тикета"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_help")
        )

        if callback.message:
            await callback.message.answer(
                "🎫 Тикет создан! Администрация свяжется с вами в ближайшее время.",
                reply_markup=builder.as_markup()
            )

    async def _back_to_help(self, callback: CallbackQuery, bot: Bot) -> None:
        """Возврат к экрану помощи"""
        await callback.answer()
        await self._show_help(callback, bot)

    async def _show_balance_history(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение истории баланса"""
        await callback.answer()

        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id

        try:
            # Получаем историю баланса
            history_data = await self.balance_service.get_user_balance_history(user_id, days=30)

            if not history_data or history_data.get("transactions_count", 0) == 0:
                builder = InlineKeyboardBuilder()
                builder.row(
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_balance")
                )

                if callback.message:
                    try:
                        await callback.message.edit_text(
                            "📊 <b>У вас пока нет истории транзакций</b> 📊\n\n"
                            f"🔍 <i>Ваши транзакции будут отображаться здесь</i>\n\n"
                            f"💡 <i>Совершите первую покупку, чтобы увидеть историю</i>",
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        self.logger.error(f"Error editing message in _show_balance_history no transactions: {e}")
                        await callback.message.answer(
                            "📊 <b>У вас пока нет истории транзакций</b> 📊\n\n"
                            f"🔍 <i>Ваши транзакции будут отображаться здесь</i>\n\n"
                            f"💡 <i>Совершите первую покупку, чтобы увидеть историю</i>",
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                return

            # Форматируем сообщение
            initial_balance = history_data.get("initial_balance", 0)
            final_balance = history_data.get("final_balance", 0)
            transactions_count = history_data.get("transactions_count", 0)

            message_text = (
                f"📊 <b>История баланса за 30 дней</b> 📊\n\n"
                f"💰 <b>Начальный баланс:</b> {initial_balance:.2f} TON\n"
                f"💰 <b>Текущий баланс:</b> {final_balance:.2f} TON\n"
                f"📈 <b>Транзакций:</b> {transactions_count}\n\n"
                f"🔄 <b>Последние транзакции:</b>\n"
            )

            # Добавляем последние 5 транзакций
            transactions = history_data.get("transactions", [])[:5]
            for i, transaction in enumerate(transactions, 1):
                transaction_type = transaction.get("transaction_type", "unknown")
                amount = transaction.get("amount", 0)
                status = transaction.get("status", "unknown")
                created_at = transaction.get("created_at", "")

                # Форматируем дату
                if created_at:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        date_str = dt.strftime("%d.%m.%Y %H:%M")
                    except:
                        date_str = created_at
                else:
                    date_str = "N/A"

                # Определяем иконку и знак операции
                if transaction_type == "purchase":
                    icon = "🛒"
                    sign = "-"
                elif transaction_type == "refund":
                    icon = "💰"
                    sign = "+"
                elif transaction_type == "bonus":
                    icon = "🎁"
                    sign = "+"
                else:
                    icon = "📝"
                    sign = ""

                # Определяем цвет статуса
                if status == "completed":
                    status_color = "✅"
                elif status == "failed":
                    status_color = "❌"
                elif status == "pending":
                    status_color = "⏳"
                else:
                    status_color = "⚪"

                message_text += f"{i}. {icon} {sign}{amount:.2f} TON - {status_color} {date_str}\n"

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_balance")
            )

            if callback.message:
                try:
                    await callback.message.edit_text(
                        message_text,
                        reply_markup=builder.as_markup()
                    )
                except Exception as e:
                    self.logger.error(f"Error editing message in _show_balance_history success case: {e}")
                    await callback.message.answer(
                        message_text,
                        reply_markup=builder.as_markup()
                    )

        except Exception as e:
            self.logger.error(f"Error showing balance history for user {user_id}: {e}")

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_balance")
            )

            if callback.message:
                try:
                    await callback.message.edit_text(
                        "❌ Произошла ошибка при загрузке истории.",
                        reply_markup=builder.as_markup()
                    )
                except Exception as e:
                    self.logger.error(f"Error editing message in _show_balance_history exception case: {e}")
                    await callback.message.answer(
                        "❌ Произошла ошибка при загрузке истории.",
                        reply_markup=builder.as_markup()
                    )

    async def _check_payment_status(self, callback: CallbackQuery, bot: Bot) -> None:
        """Проверка статуса платежа"""
        await callback.answer()

        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id
        payment_id = callback.data.replace("check_payment_", "")

        try:
            # Проверяем статус через сервис покупки звезд
            status_result = await self.star_purchase_service.check_purchase_status(payment_id)

            if status_result.get("status") == "failed":
                error_msg = status_result.get("error", "Неизвестная ошибка")
                
                # Используем универсальный обработчик ошибок
                error_type = await self._handle_purchase_error(Exception(error_msg), {"user_id": user_id, "payment_id": payment_id})
                
                # Показываем ошибку с рекомендациями
                await self._show_error_with_suggestions(callback, error_type, {"user_id": user_id, "payment_id": payment_id, "error": error_msg})
                return

            # Форматируем сообщение о статусе
            payment_status = status_result.get("status", "unknown")
            amount = status_result.get("amount", 0)
            currency = status_result.get("currency", "TON")

            # Определяем сообщение в зависимости от статуса
            if payment_status == "paid":
                status_message = "✅ Оплата подтверждена!"
                status_color = "✅"
            elif payment_status == "pending":
                status_message = "⏳ Оплата в процессе..."
                status_color = "⏳"
            elif payment_status == "failed":
                status_message = "❌ Оплата не удалась"
                status_color = "❌"
            elif payment_status == "cancelled":
                status_message = "❌ Оплата отменена"
                status_color = "❌"
            else:
                status_message = "❓ Неизвестный статус"
                status_color = "❓"

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"check_payment_{payment_id}"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
            )

            if callback.message:
                try:
                    await callback.message.edit_text(
                        f"📋 <b>Статус платежа</b> 📋\n\n"
                        f"💳 <b>Сумма:</b> {amount} {currency}\n"
                        f"📊 <b>Статус:</b> {status_color} {status_message}\n"
                        f"🔢 <b>ID платежа:</b> {payment_id}\n\n"
                        f"🔄 <i>Обновите статус для получения актуальной информации</i>",
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Error editing message in _check_payment_status success case: {e}")
                    await callback.message.answer(
                        f"📋 Статус платежа\n\n"
                        f"💳 Сумма: {amount} {currency}\n"
                        f"📊 Статус: {status_color} {status_message}\n"
                        f"🔢 ID платежа: {payment_id}",
                        reply_markup=builder.as_markup()
                    )

        except Exception as e:
            self.logger.error(f"Error checking payment status for {payment_id}: {e}")
            
            # Используем универсальный обработчик ошибок
            error_type = await self._handle_purchase_error(e, {"user_id": user_id, "payment_id": payment_id})
            
            # Показываем ошибку с рекомендациями
            await self._show_error_with_suggestions(callback, error_type, {"user_id": user_id, "payment_id": payment_id, "error": str(e)})

    async def _show_recharge_custom_amount(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение экрана ввода суммы для пополнения"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="💰 10 TON", callback_data="recharge_10"),
            InlineKeyboardButton(text="💰 50 TON", callback_data="recharge_50")
        )
        builder.row(
            InlineKeyboardButton(text="💰 100 TON", callback_data="recharge_100"),
            InlineKeyboardButton(text="💰 500 TON", callback_data="recharge_500")
        )
        builder.row(
            InlineKeyboardButton(text="🎯 Своя сумма", callback_data="recharge_custom_amount"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_balance")
        )

        if callback.message:
            try:
                await callback.message.edit_text(
                    "Выберите сумму для пополнения:",
                    reply_markup=builder.as_markup()
                )
            except Exception as e:
                self.logger.error(f"Error editing message in _show_recharge_custom_amount: {e}")
                await callback.message.answer(
                    "Выберите сумму для пополнения:",
                    reply_markup=builder.as_markup()
                )

    async def _handle_recharge_amount(self, callback: CallbackQuery, bot: Bot, amount: float) -> None:
        """Обработка создания пополнения с указанной суммой"""
        await callback.answer()

        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id

        try:
            # Используем сервис покупки звезд для создания пополнения
            recharge_result = await self.star_purchase_service.create_recharge(user_id, amount)

            if recharge_result["status"] == "failed":
                error_msg = recharge_result.get("error", "Неизвестная ошибка")
                
                # Используем универсальный обработчик ошибок
                error_type = await self._handle_purchase_error(Exception(error_msg), {"user_id": user_id, "amount": amount})
                
                # Показываем ошибку с рекомендациями
                await self._show_error_with_suggestions(callback, error_type, {"user_id": user_id, "amount": amount, "error": error_msg})
                return

            result = recharge_result.get("result", {})
            transaction_id = recharge_result.get("transaction_id")

            if not result or "uuid" not in result or "url" not in result:
                if callback.message:
                    try:
                        await callback.message.edit_text("❌ Ошибка: некорректные данные от платежной системы")
                    except Exception as e:
                        self.logger.error(f"Error editing message in _handle_recharge_amount data error case: {e}")
                        await callback.message.answer("❌ Ошибка: некорректные данные от платежной системы")
                return

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text="🔍 Проверить оплату",
                    callback_data=f"check_recharge_{result['uuid']}"
                )
            )
            builder.row(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="recharge_custom"
                )
            )

            if callback.message:
                try:
                    await callback.message.edit_text(
                        f"✅ <b>Создан счет на пополнение баланса на {amount} TON</b> ✅\n\n"
                        f"💳 <b>Ссылка на оплату:</b> {result['url']}\n\n"
                        f"📋 <b>ID счета:</b> {result['uuid']}\n"
                        f"🔢 <b>ID транзакции:</b> {transaction_id}\n\n"
                        f"🔗 <i>Перейдите по ссылке для оплаты</i>\n"
                        f"⏰ <i>Счет действителен в течение 15 минут</i>",
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Error editing message in _handle_recharge_amount success case: {e}")
                    await callback.message.answer(
                        f"✅ Создан счет на пополнение баланса на {amount} TON.\n\n"
                        f"💳 Ссылка на оплату: {result['url']}\n\n"
                        f"📋 ID счета: {result['uuid']}\n"
                        f"🔢 ID транзакции: {transaction_id}",
                        reply_markup=builder.as_markup()
                    )

        except Exception as e:
            self.logger.error(f"Error creating recharge for user {user_id}: {e}")
            
            # Используем универсальный обработчик ошибок
            error_type = await self._handle_purchase_error(e, {"user_id": user_id, "amount": amount})
            
            # Показываем ошибку с рекомендациями
            await self._show_error_with_suggestions(callback, error_type, {"user_id": user_id, "amount": amount, "error": str(e)})

    async def _handle_recharge_custom_amount_input(self, message: Message, bot: Bot) -> None:
        """Обработка ввода пользовательской суммы для пополнения с улучшенной валидацией"""
        if not message.from_user or not message.from_user.id:
            return

        user_id = message.from_user.id

        try:
            # Улучшенная валидация ввода
            input_text = message.text.strip()
            
            # Проверка на пустую строку
            if not input_text:
                await message.answer("❌ Пожалуйста, введите сумму для пополнения")
                return
                
            # Проверка на наличие только цифр и точки
            if not all(c.isdigit() or c == '.' for c in input_text):
                await message.answer("❌ Пожалуйста, введите корректную сумму (только цифры и точка)")
                return
                
            # Проверка на несколько точек
            if input_text.count('.') > 1:
                await message.answer("❌ Пожалуйста, введите корректную сумму (только одна точка)")
                return

            amount = float(input_text)

            # Расширенная валидация суммы
            if amount <= 0:
                await message.answer("❌ Сумма должна быть больше 0 TON")
                return
            if amount < 10:
                await message.answer("❌ Минимальная сумма для пополнения - 10 TON")
                return
            if amount > 10000:
                await message.answer("❌ Максимальная сумма для пополнения - 10000 TON")
                return
            # Проверка на слишком маленькие суммы (менее 0.01 TON)
            if amount < 0.01:
                await message.answer("❌ Минимальная сумма для пополнения - 0.01 TON")
                return

            # Используем сервис покупки звезд для создания пополнения
            recharge_result = await self.star_purchase_service.create_recharge(user_id, amount)

            if recharge_result["status"] == "failed":
                error_msg = recharge_result.get("error", "Неизвестная ошибка")
                
                # Используем универсальный обработчик ошибок
                error_type = await self._handle_purchase_error(Exception(error_msg), {"user_id": user_id, "amount": amount})
                
                # Показываем ошибку с рекомендациями
                await self._show_error_with_suggestions(message, error_type, {"user_id": user_id, "amount": amount, "error": error_msg})
                return

            result = recharge_result.get("result", {})
            transaction_id = recharge_result.get("transaction_id")

            if not result or "uuid" not in result or "url" not in result:
                await message.answer("❌ Ошибка: некорректные данные от платежной системы")
                return

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text="🔍 Проверить оплату",
                    callback_data=f"check_recharge_{result['uuid']}"
                )
            )
            builder.row(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="recharge_custom"
                )
            )

            await message.answer(
                f"✅ Создан счет на пополнение баланса на {amount} TON.\n\n"
                f"💳 Ссылка на оплату: {result['url']}\n\n"
                f"📋 ID счета: {result['uuid']}\n"
                f"🔢 ID транзакции: {transaction_id}",
                reply_markup=builder.as_markup()
            )

        except ValueError:
            await message.answer("❌ Пожалуйста, введите корректную сумму числом")
        except Exception as e:
            self.logger.error(f"Error creating custom recharge for user {user_id}: {e}")
            
            # Используем универсальный обработчик ошибок
            error_type = await self._handle_purchase_error(e, {"user_id": user_id, "amount": amount})
            
            # Показываем ошибку с рекомендациями
            await self._show_error_with_suggestions(message, error_type, {"user_id": user_id, "amount": amount, "error": str(e)})

    async def _check_recharge_status(self, callback: CallbackQuery, bot: Bot) -> None:
        """Проверка статуса пополнения"""
        await callback.answer()

        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id
        payment_id = callback.data.replace("check_recharge_", "")

        try:
            # Проверяем статус через сервис покупки звезд
            status_result = await self.star_purchase_service.check_recharge_status(payment_id)

            if status_result.get("status") == "failed":
                error_msg = status_result.get("error", "Неизвестная ошибка")
                
                # Используем универсальный обработчик ошибок
                error_type = await self._handle_purchase_error(Exception(error_msg), {"user_id": user_id, "payment_id": payment_id})
                
                # Показываем ошибку с рекомендациями
                await self._show_error_with_suggestions(callback, error_type, {"user_id": user_id, "payment_id": payment_id, "error": error_msg})
                return

            # Форматируем сообщение о статусе
            payment_status = status_result.get("status", "unknown")
            amount = status_result.get("amount", 0)
            currency = status_result.get("currency", "TON")

            # Определяем сообщение в зависимости от статуса
            if payment_status == "paid":
                status_message = "✅ Оплата подтверждена! Баланс успешно пополнен."
                status_color = "✅"
            elif payment_status == "pending":
                status_message = "⏳ Оплата в процессе..."
                status_color = "⏳"
            elif payment_status == "failed":
                status_message = "❌ Оплата не удалась"
                status_color = "❌"
            elif payment_status == "cancelled":
                status_message = "❌ Оплата отменена"
                status_color = "❌"
            else:
                status_message = "❓ Неизвестный статус"
                status_color = "❓"

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="🔄 Обновить", callback_data=f"check_recharge_{payment_id}"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data="recharge_custom")
            )

            if callback.message:
                try:
                    await callback.message.edit_text(
                        f"📋 <b>Статус пополнения</b> 📋\n\n"
                        f"💳 <b>Сумма:</b> {amount} {currency}\n"
                        f"📊 <b>Статус:</b> {status_color} {status_message}\n"
                        f"🔢 <b>ID платежа:</b> {payment_id}\n\n"
                        f"🔄 <i>Обновите статус для получения актуальной информации</i>",
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    self.logger.error(f"Error editing message in _check_recharge_status success case: {e}")
                    await callback.message.answer(
                        f"📋 Статус пополнения\n\n"
                        f"💳 Сумма: {amount} {currency}\n"
                        f"📊 Статус: {status_color} {status_message}\n"
                        f"🔢 ID платежа: {payment_id}",
                        reply_markup=builder.as_markup()
                    )

        except Exception as e:
            self.logger.error(f"Error checking recharge status for {payment_id}: {e}")
            
            # Используем универсальный обработчик ошибок
            error_type = await self._handle_purchase_error(e, {"user_id": user_id, "payment_id": payment_id})
            
            # Показываем ошибку с рекомендациями
            await self._show_error_with_suggestions(callback, error_type, {"user_id": user_id, "payment_id": payment_id, "error": str(e)})

    async def _handle_error_action(self, callback: CallbackQuery, bot: Bot) -> None:
        """Обработка действий после ошибок"""
        await callback.answer()
        
        if not callback.from_user or not callback.from_user.id:
            return
            
        user_id = callback.from_user.id
        action = callback.data.replace("error_action_", "")
        
        self.logger.info(f"User {user_id} selected error action: {action}")
        
        # Обработка различных действий после ошибок
        if action == "recharge":
            # Перенаправление на пополнение баланса
            await self._handle_recharge(callback, bot)
        elif action == "reduce_amount":
            # Показываем меню покупки звезд с меньшими суммами
            await self._show_buy_stars(callback, bot)
        elif action == "alternative_payment":
            # Показываем меню с альтернативными способами оплаты
            await self._handle_recharge(callback, bot)
        elif action == "check_connection":
            # Показываем сообщение о проверке соединения
            await callback.message.answer("📡 <b>Проверьте интернет-соединение</b> 📡\n\n"
                                        "🔍 <i>Убедитесь, что у вас есть стабильное подключение к интернету</i>\n\n"
                                        "🔄 <i>Попробуйте снова через 30 секунд</i>\n\n"
                                        "💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                                        parse_mode="HTML")
        elif action == "retry_later":
            # Показываем сообщение о повторной попытке
            await callback.message.answer("⏰ <b>Попробуйте снова позже</b> ⏰\n\n"
                                        "🔄 <i>Система временно недоступна</i>\n\n"
                                        "⏳ <i>Попробуйте обновить страницу через 5 минут</i>\n\n"
                                        "💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                                        parse_mode="HTML")
        elif action == "retry":
            # Показываем сообщение о повторной попытке
            await callback.message.answer("🔄 <b>Повторная попытка</b> 🔄\n\n"
                                        "⚡ <i>Система пытается обработать ваш запрос снова</i>\n\n"
                                        "🔧 <i>Это может занять несколько секунд</i>\n\n"
                                        "💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                                        parse_mode="HTML")
        elif action == "support":
            # Показываем экран помощи
            await self._show_help(callback, bot)
        else:
            # По умолчанию возвращаем в главное меню
            await self._back_to_main(callback, bot)

    async def _handle_back_to_menu(self, callback: CallbackQuery, bot: Bot) -> None:
        """Обработка возврата в меню после ошибок"""
        await callback.answer()
        
        if not callback.from_user or not callback.from_user.id:
            return
            
        user_id = callback.from_user.id
        menu_name = callback.data.replace("back_to_", "").replace("_", " ").title()
        
        self.logger.info(f"User {user_id} wants to go back to: {menu_name}")
        
        # Обработка возврата в различные меню
        if "Main" in menu_name or "Главное" in menu_name:
            await self._back_to_main(callback, bot)
        elif "Balance" in menu_name or "Баланс" in menu_name:
            await self._show_balance(callback, bot)
        elif "Stars" in menu_name or "Звезд" in menu_name or "Магазин" in menu_name:
            await self._show_buy_stars(callback, bot)
        elif "Recharge" in menu_name or "Пополнение" in menu_name:
            await self._handle_recharge(callback, bot)
        elif "Help" in menu_name or "Помощь" in menu_name:
            await self._show_help(callback, bot)
        else:
            # По умолчанию возвращаем в главное меню
            await self._back_to_main(callback, bot)
