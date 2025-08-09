"""
Обработчик сообщений с интеграцией сессий и кеширования
"""
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, User
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Dict, Any, Optional
from core.interfaces import EventHandlerInterface
from repositories.user_repository import UserRepository
from services.payment_service import PaymentService
from services.session_cache import SessionCache
from services.rate_limit_cache import RateLimitCache
from services.payment_cache import PaymentCache


class MessageHandler(EventHandlerInterface):
    """Обработчик сообщений с поддержкой сессий и кеширования"""

    def __init__(self,
                 user_repository: UserRepository,
                 payment_service: PaymentService,
                 session_cache: Optional[SessionCache] = None,
                 rate_limit_cache: Optional[RateLimitCache] = None,
                 payment_cache: Optional[PaymentCache] = None):
        self.user_repository = user_repository
        self.payment_service = payment_service
        self.session_cache = session_cache
        self.rate_limit_cache = rate_limit_cache
        self.payment_cache = payment_cache

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
        elif callback_data == "buy_stars":
            await self._show_buy_stars(callback, bot)
        elif callback_data == "custom_amount":
            await self._show_custom_amount(callback, bot)
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
        elif callback_data == "help":
            await self._show_help(callback, bot)
        elif callback_data == "create_ticket":
            await self._create_ticket(callback, bot)
        elif callback_data == "back_to_help":
            await self._back_to_help(callback, bot)

    def register_handlers(self, dp: Dispatcher) -> None:
        """Регистрация обработчиков"""
        # Обработка команды /start
        dp.message.register(self.cmd_start, Command("start"))

        # Обработка текстовых сообщений
        dp.message.register(self.handle_message)

        # Обработка callback
        dp.callback_query.register(self.handle_callback)

    async def cmd_start(self, message: Message) -> None:
        """Обработка команды /start с созданием сессии"""
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
            InlineKeyboardButton(text="1-Баланс", callback_data="balance"),
            InlineKeyboardButton(text="2-Покупка Звезд", callback_data="buy_stars"),
            InlineKeyboardButton(text="3-Помощь", callback_data="help")
        )

        await message.answer(
            "🌟 Добро пожаловать в наш бот!\n\n"
            "Выберите действие:\n"
            "1-Баланс\n"
            "2-Покупка Звезд\n"
            "3-Помощь",
            reply_markup=builder.as_markup()
        )

    async def _handle_message_with_session(self, message: Message, bot: Bot, session_data: dict) -> None:
        """Обработка сообщения с сохранением состояния сессии"""
        # Проверяем, является ли сообщение числом для покупки звезд
        if message.text and message.text.isdigit():
            amount = int(message.text)
            if 1 <= amount <= 10000:
                await self._create_star_purchase_custom(message, bot, amount)
            else:
                await message.answer("❌ Пожалуйста, введите сумму от 1 до 10000 звезд")
        else:
            await message.answer("✅ Ваше сообщение получено. Спасибо за использование бота!")

    async def _create_new_session(self, message: Message, bot: Bot) -> None:
        """Создание новой сессии пользователя"""
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

    async def _handle_message_without_session(self, message: Message, bot: Bot) -> None:
        """Обработка сообщения без сессий"""
        # Проверяем, является ли сообщение числом для покупки звезд
        if message.text and message.text.isdigit():
            amount = int(message.text)
            if 1 <= amount <= 10000:
                await self._create_star_purchase_custom(message, bot, amount)
            else:
                await message.answer("❌ Пожалуйста, введите сумму от 1 до 10000 звезд")
        else:
            await message.answer("✅ Ваше сообщение получено. Спасибо за использование бота!")

    async def _show_balance(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение баланса пользователя"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="💳 Пополнить", callback_data="recharge"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
        )

        if callback.message:
            await callback.message.answer(
                "💰 Ваш баланс:\n\n"
                "⭐ 1000 звезд",
                reply_markup=builder.as_markup()
            )

    async def _handle_recharge(self, callback: CallbackQuery, bot: Bot) -> None:
        """Обработка выбора способа пополнения"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="💳 Пополнить через Heleket", callback_data="recharge_heleket"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_balance")
        )

        if callback.message:
            await callback.message.answer(
                "Выберите способ пополнения:",
                reply_markup=builder.as_markup()
            )

    async def _back_to_main(self, callback: CallbackQuery, bot: Bot) -> None:
        """Возврат в главное меню"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="1-Баланс", callback_data="balance"),
            InlineKeyboardButton(text="2-Покупка Звезд", callback_data="buy_stars"),
            InlineKeyboardButton(text="3-Помощь", callback_data="help")
        )

        if callback.message:
            await callback.message.answer(
                "🌟 Добро пожаловать в наш бот!\n\n"
                "Выберите действие:\n"
                "1-Баланс\n"
                "2-Покупка Звезд\n"
                "3-Помощь",
                reply_markup=builder.as_markup()
            )

    async def _back_to_balance(self, callback: CallbackQuery, bot: Bot) -> None:
        """Возврат к экрану баланса"""
        await callback.answer()
        await self._show_balance(callback, bot)

    async def _show_buy_stars(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение экрана покупки звезд"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⭐ 100 звезд", callback_data="buy_100"),
            InlineKeyboardButton(text="⭐ 250 звезд", callback_data="buy_250")
        )
        builder.row(
            InlineKeyboardButton(text="⭐ 500 звезд", callback_data="buy_500"),
            InlineKeyboardButton(text="⭐ 1000 звезд", callback_data="buy_1000")
        )
        builder.row(
            InlineKeyboardButton(text="🎯 Своя сумма", callback_data="custom_amount"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
        )

        if callback.message:
            await callback.message.answer(
                "Выберите пакет звезд:",
                reply_markup=builder.as_markup()
            )

    async def _show_custom_amount(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение экрана ввода своей суммы"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
        )

        if callback.message:
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
            # Кеширование информации о покупке
            if self.payment_cache:
                await self.payment_cache.cache_payment_details(
                    f"purchase_{user_id}_{amount}",
                    {"amount": amount, "user_id": user_id, "status": "pending"}
                )

            invoice = await self.payment_service.create_invoice_for_user(user_id, str(amount))

            if "error" in invoice or "status" in invoice and invoice["status"] == "failed":
                error_msg = invoice.get("error", "Неизвестная ошибка")
                if callback.message:
                    await callback.message.answer(f"❌ Ошибка при создании счета: {error_msg}")
                return

            if "result" not in invoice:
                if callback.message:
                    await callback.message.answer("❌ Ошибка: некорректный ответ от платежной системы")
                return

            result = invoice["result"]
            if "uuid" not in result or "url" not in result:
                if callback.message:
                    await callback.message.answer("❌ Ошибка: неполные данные в ответе от платежной системы")
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
                await callback.message.answer(
                    f"✅ Создан счет на покупку {amount} звезд.\n\n"
                    f"💳 Ссылка на оплату: {result['url']}\n\n"
                    f"📋 ID счета: {result['uuid']}",
                    reply_markup=builder.as_markup()
                )

        except Exception as e:
            if callback.message:
                await callback.message.answer(f"❌ Произошла ошибка: {str(e)}")

    async def _create_star_purchase_custom(self, message: Message, bot: Bot, amount: int) -> None:
        """Создание покупки звезд для пользовательской суммы"""
        if not message.from_user or not message.from_user.id:
            return

        user_id = message.from_user.id

        try:
            invoice = await self.payment_service.create_invoice_for_user(user_id, str(amount))

            if "error" in invoice or "status" in invoice and invoice["status"] == "failed":
                error_msg = invoice.get("error", "Неизвестная ошибка")
                await message.answer(f"❌ Ошибка при создании счета: {error_msg}")
                return

            if "result" not in invoice:
                await message.answer("❌ Ошибка: некорректный ответ от платежной системы")
                return

            result = invoice["result"]
            if "uuid" not in result or "url" not in result:
                await message.answer("❌ Ошибка: неполные данные в ответе от платежной системы")
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
                f"📋 ID счета: {result['uuid']}",
                reply_markup=builder.as_markup()
            )

        except Exception as e:
            await message.answer(f"❌ Произошла ошибка: {str(e)}")

    async def _show_help(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение экрана помощи"""
        await callback.answer()

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🎫 Создать тикет", callback_data="create_ticket"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
        )

        if callback.message:
            await callback.message.answer(
                "🤖 Помощь\n\n"
                "Этот бот позволяет вам:\n"
                "• Проверять баланс звезд\n"
                "• Покупать звезды через Heleket\n"
                "• Получать поддержку от администрации\n\n"
                "Звезды можно использовать для различных функций внутри бота.",
                reply_markup=builder.as_markup()
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
