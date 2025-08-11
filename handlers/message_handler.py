"""
Обработчик сообщений с интеграцией сессий и кеширования
"""
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, User
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Dict, Any, Optional
from core.interfaces import EventHandlerInterface
from repositories.user_repository import UserRepository
from repositories.balance_repository import BalanceRepository
from services.payment_service import PaymentService
from services.balance_service import BalanceService
from services.star_purchase_service import StarPurchaseService
from services.session_cache import SessionCache
from services.rate_limit_cache import RateLimitCache
from services.payment_cache import PaymentCache


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
                await callback.message.answer("Введите сумму для пополнения (от 10 до 10000 TON):")
        elif callback_data.startswith("check_recharge_"):
            await self._check_recharge_status(callback, bot)
        elif callback_data == "buy_stars":
            await self._show_buy_stars(callback, bot)
        elif callback_data == "buy_stars_with_balance":
            await self._show_buy_stars_with_balance(callback, bot)
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
        elif callback_data == "recharge_custom":
            await self._show_recharge_custom_amount(callback, bot)
        elif callback_data.startswith("check_recharge_"):
            await self._check_recharge_status(callback, bot)

    def register_handlers(self, dp: Dispatcher) -> None:
        """Регистрация обработчиков"""
        # Обработка команды /start
        dp.message.register(self.cmd_start, Command("start"))

        # Обработка текстовых сообщений
        dp.message.register(self.handle_message)

        # Обработка callback
        dp.callback_query.register(self.handle_callback)

    async def cmd_start(self, message: Message, bot: Bot) -> None:
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

        # Проверяем, является ли сообщение числом для покупки звезд с баланса
        if message.text and message.text.isdigit():
            amount = int(message.text)
            if 1 <= amount <= 10000:
                await self._create_star_purchase_custom_balance(message, bot, amount)
            else:
                await message.answer("❌ Пожалуйста, введите количество звезд от 1 до 10000")

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
            # Проверяем, является ли сообщение числом для пополнения баланса
            if message.text and message.text.replace('.', '', 1).isdigit():
                amount = float(message.text)
                if 10 <= amount <= 10000:
                    await self._handle_recharge_custom_amount_input(message, bot)
                else:
                    await message.answer("❌ Пожалуйста, введите сумму для пополнения от 10 до 10000 TON")
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

        # Проверяем, является ли сообщение числом для покупки звезд с баланса
        if message.text and message.text.isdigit():
            amount = int(message.text)
            if 1 <= amount <= 10000:
                await self._create_star_purchase_custom_balance(message, bot, amount)
            else:
                await message.answer("❌ Пожалуйста, введите количество звезд от 1 до 10000")

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
            # Проверяем, является ли сообщение числом для пополнения баланса
            if message.text and message.text.replace('.', '', 1).isdigit():
                amount = float(message.text)
                if 10 <= amount <= 10000:
                    await self._handle_recharge_custom_amount_input(message, bot)
                else:
                    await message.answer("❌ Пожалуйста, введите сумму для пополнения от 10 до 10000 TON")
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
                    InlineKeyboardButton(text="💳 Пополнить", callback_data="recharge"),
                    InlineKeyboardButton(text="📊 История", callback_data="balance_history"),
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
                )

                if callback.message:
                    await callback.message.answer(
                        f"💰 Ваш баланс:\n\n"
                        f"⭐ {balance:.2f} {currency}\n"
                        f"📊 Источник: {source}",
                        reply_markup=builder.as_markup()
                    )
            else:
                # Если не удалось получить баланс, показываем ошибку
                builder = InlineKeyboardBuilder()
                builder.row(
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
                )

                if callback.message:
                    await callback.message.answer(
                        "❌ Не удалось получить баланс. Пожалуйста, попробуйте позже.",
                        reply_markup=builder.as_markup()
                    )

        except Exception as e:
            self.logger.error(f"Error showing balance for user {user_id}: {e}")

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
            )

            if callback.message:
                await callback.message.answer(
                    "❌ Произошла ошибка при получении баланса.",
                    reply_markup=builder.as_markup()
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
        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id
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

        if callback.message:
            await callback.message.answer(
                "Выберите пакет звезд:",
                reply_markup=builder.as_markup()
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
            InlineKeyboardButton(text=f"⭐ 100 звезд ({100} TON)", callback_data="buy_100_balance"),
            InlineKeyboardButton(text=f"⭐ 250 звезд ({250} TON)", callback_data="buy_250_balance")
        )
        builder.row(
            InlineKeyboardButton(text=f"⭐ 500 звезд ({500} TON)", callback_data="buy_500_balance"),
            InlineKeyboardButton(text=f"⭐ 1000 звезд ({1000} TON)", callback_data="buy_1000_balance")
        )
        builder.row(
            InlineKeyboardButton(text="🎯 Своя сумма", callback_data="custom_amount_balance"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
        )

        if callback.message:
            await callback.message.answer(
                f"💰 Ваш баланс: {balance:.2f} TON\n\n"
                "Выберите пакет звезд для покупки с баланса:",
                reply_markup=builder.as_markup()
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
            # Используем новый сервис покупки звезд с баланса
            purchase_result = await self.star_purchase_service.create_star_purchase(
                user_id=user_id,
                amount=amount,
                purchase_type="balance"
            )

            if purchase_result["status"] == "failed":
                error_msg = purchase_result.get("error", "Неизвестная ошибка")

                # Если недостаточно средств, показываем баланс
                if "Insufficient balance" in error_msg:
                    balance_data = await self.balance_service.get_user_balance(user_id)
                    balance = balance_data.get("balance", 0) if balance_data else 0

                    builder = InlineKeyboardBuilder()
                    builder.row(
                        InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="recharge"),
                        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
                    )

                    if callback.message:
                        await callback.message.answer(
                            f"❌ Недостаточно средств!\n\n"
                            f"💰 Ваш баланс: {balance:.2f} TON\n"
                            f"💸 Требуется: {amount} TON\n\n"
                            f"Пополните баланс для покупки звезд.",
                            reply_markup=builder.as_markup()
                        )
                else:
                    builder = InlineKeyboardBuilder()
                    builder.row(
                        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
                    )

                    if callback.message:
                        await callback.message.answer(
                            f"❌ Ошибка при покупке: {error_msg}",
                            reply_markup=builder.as_markup()
                        )
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

            if callback.message:
                await callback.message.answer(
                    f"✅ Покупка успешна!\n\n"
                    f"⭐ Куплено звезд: {stars_count}\n"
                    f"💰 Баланс до: {old_balance:.2f} TON\n"
                    f"💰 Баланс после: {new_balance:.2f} TON\n\n"
                    f"Спасибо за покупку!",
                    reply_markup=builder.as_markup()
                )

        except Exception as e:
            self.logger.error(f"Error creating star purchase with balance for user {user_id}: {e}")

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
            )

            if callback.message:
                await callback.message.answer(
                    f"❌ Произошла ошибка: {str(e)}",
                    reply_markup=builder.as_markup()
                )

    async def _show_custom_amount_balance(self, callback: CallbackQuery, bot: Bot) -> None:
        """Отображение экрана ввода своей суммы для покупки с баланса"""
        await callback.answer()

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

                # Если недостаточно средств, показываем баланс
                if "Insufficient balance" in error_msg:
                    balance_data = await self.balance_service.get_user_balance(user_id)
                    balance = balance_data.get("balance", 0) if balance_data else 0

                    await message.answer(
                        f"❌ Недостаточно средств!\n\n"
                        f"💰 Ваш баланс: {balance:.2f} TON\n"
                        f"💸 Требуется: {amount} TON\n\n"
                        f"Пополните баланс для покупки звезд."
                    )
                else:
                    await message.answer(f"❌ Ошибка при покупке: {error_msg}")
                return

            # Показываем успешное сообщение
            old_balance = purchase_result.get("old_balance", 0)
            new_balance = purchase_result.get("new_balance", 0)
            stars_count = purchase_result.get("stars_count", 0)

            await message.answer(
                f"✅ Покупка успешна!\n\n"
                f"⭐ Куплено звезд: {stars_count}\n"
                f"💰 Баланс до: {old_balance:.2f} TON\n"
                f"💰 Баланс после: {new_balance:.2f} TON\n\n"
                f"Спасибо за покупку!"
            )

        except Exception as e:
            self.logger.error(f"Error creating custom star purchase with balance for user {user_id}: {e}")
            await message.answer(f"❌ Произошла ошибка: {str(e)}")

        # Получаем баланс пользователя
        balance_data = await self.balance_service.get_user_balance(callback.from_user.id)
        balance = balance_data.get("balance", 0) if balance_data else 0

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
        )

        if callback.message:
            await callback.message.answer(
                f"💰 Ваш баланс: {balance:.2f} TON\n\n"
                "Введите количество звезд для покупки с баланса (1-10000):",
                reply_markup=builder.as_markup()
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
            # Используем новый сервис покупки звезд
            purchase_result = await self.star_purchase_service.create_star_purchase(user_id, amount)

            if purchase_result["status"] == "failed":
                error_msg = purchase_result.get("error", "Неизвестная ошибка")
                if callback.message:
                    await callback.message.answer(f"❌ Ошибка при создании покупки: {error_msg}")
                return

            result = purchase_result.get("result", {})
            transaction_id = purchase_result.get("transaction_id")

            if not result or "uuid" not in result or "url" not in result:
                if callback.message:
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
                await callback.message.answer(
                    f"✅ Создан счет на покупку {amount} звезд.\n\n"
                    f"💳 Ссылка на оплату: {result['url']}\n\n"
                    f"📋 ID счета: {result['uuid']}\n"
                    f"🔢 ID транзакции: {transaction_id}",
                    reply_markup=builder.as_markup()
                )

        except Exception as e:
            self.logger.error(f"Error creating star purchase for user {user_id}: {e}")
            if callback.message:
                await callback.message.answer(f"❌ Произошла ошибка: {str(e)}")

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
                await message.answer(f"❌ Ошибка при создании покупки: {error_msg}")
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
                    await callback.message.answer(
                        "📊 У вас пока нет истории транзакций.",
                        reply_markup=builder.as_markup()
                    )
                return

            # Форматируем сообщение
            initial_balance = history_data.get("initial_balance", 0)
            final_balance = history_data.get("final_balance", 0)
            transactions_count = history_data.get("transactions_count", 0)

            message_text = (
                f"📊 История баланса за 30 дней\n\n"
                f"💰 Начальный баланс: {initial_balance:.2f} TON\n"
                f"💰 Текущий баланс: {final_balance:.2f} TON\n"
                f"📈 Транзакций: {transactions_count}\n\n"
                f"Последние транзакции:\n"
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

                builder = InlineKeyboardBuilder()
                builder.row(
                    InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"check_payment_{payment_id}"),
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
                )

                if callback.message:
                    await callback.message.answer(
                        f"❌ Ошибка проверки статуса: {error_msg}",
                        reply_markup=builder.as_markup()
                    )
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
                await callback.message.answer(
                    f"📋 Статус платежа\n\n"
                    f"💳 Сумма: {amount} {currency}\n"
                    f"📊 Статус: {status_color} {status_message}\n"
                    f"🔢 ID платежа: {payment_id}",
                    reply_markup=builder.as_markup()
                )

        except Exception as e:
            self.logger.error(f"Error checking payment status for {payment_id}: {e}")

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
            )

            if callback.message:
                await callback.message.answer(
                    "❌ Произошла ошибка при проверке статуса.",
                    reply_markup=builder.as_markup()
                )

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
                if callback.message:
                    await callback.message.answer(f"❌ Ошибка при создании пополнения: {error_msg}")
                return

            result = recharge_result.get("result", {})
            transaction_id = recharge_result.get("transaction_id")

            if not result or "uuid" not in result or "url" not in result:
                if callback.message:
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
                await callback.message.answer(
                    f"✅ Создан счет на пополнение баланса на {amount} TON.\n\n"
                    f"💳 Ссылка на оплату: {result['url']}\n\n"
                    f"📋 ID счета: {result['uuid']}\n"
                    f"🔢 ID транзакции: {transaction_id}",
                    reply_markup=builder.as_markup()
                )

        except Exception as e:
            self.logger.error(f"Error creating recharge for user {user_id}: {e}")
            if callback.message:
                await callback.message.answer(f"❌ Произошла ошибка: {str(e)}")

    async def _handle_recharge_custom_amount_input(self, message: Message, bot: Bot) -> None:
        """Обработка ввода пользовательской суммы для пополнения"""
        if not message.from_user or not message.from_user.id:
            return

        user_id = message.from_user.id

        try:
            amount = float(message.text)

            # Валидация суммы
            if amount < 10:
                await message.answer("❌ Минимальная сумма для пополнения - 10 TON")
                return
            if amount > 10000:
                await message.answer("❌ Максимальная сумма для пополнения - 10000 TON")
                return

            # Используем сервис покупки звезд для создания пополнения
            recharge_result = await self.star_purchase_service.create_recharge(user_id, amount)

            if recharge_result["status"] == "failed":
                error_msg = recharge_result.get("error", "Неизвестная ошибка")
                await message.answer(f"❌ Ошибка при создании пополнения: {error_msg}")
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
            await message.answer(f"❌ Произошла ошибка: {str(e)}")

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

                builder = InlineKeyboardBuilder()
                builder.row(
                    InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"check_recharge_{payment_id}"),
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="recharge_custom")
                )

                if callback.message:
                    await callback.message.answer(
                        f"❌ Ошибка проверки статуса: {error_msg}",
                        reply_markup=builder.as_markup()
                    )
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
                await callback.message.answer(
                    f"📋 Статус пополнения\n\n"
                    f"💳 Сумма: {amount} {currency}\n"
                    f"📊 Статус: {status_color} {status_message}\n"
                    f"🔢 ID платежа: {payment_id}",
                    reply_markup=builder.as_markup()
                )

        except Exception as e:
            self.logger.error(f"Error checking recharge status for {payment_id}: {e}")

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="⬅️ Назад", callback_data="recharge_custom")
            )

            if callback.message:
                await callback.message.answer(
                    "❌ Произошла ошибка при проверке статуса.",
                    reply_markup=builder.as_markup()
                )
