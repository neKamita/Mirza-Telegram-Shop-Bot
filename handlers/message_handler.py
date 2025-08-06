"""
Обработчик сообщений
"""
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Dict, Any
from core.interfaces import EventHandlerInterface
from repositories.user_repository import UserRepository
from services.payment_service import PaymentService


class MessageHandler(EventHandlerInterface):
    """Обработчик сообщений и команд"""

    def __init__(self, user_repository: UserRepository, payment_service: PaymentService):
        self.user_repository = user_repository
        self.payment_service = payment_service

    async def handle_message(self, message: Message, bot: Bot) -> None:
        """Обработка текстового сообщения"""
        user_id = message.from_user.id

        # Проверка, является ли пользователь премиум
        is_premium = await self.user_repository.user_exists(user_id)

        if not is_premium:
            await self._send_payment_request(message, bot)
            return

        # Подтверждение получения сообщения для премиум пользователей
        await message.answer("✅ Ваше сообщение получено. Спасибо за использование бота!")

    async def handle_callback(self, callback: CallbackQuery, bot: Bot) -> None:
        """Обработка callback запросов"""
        callback_data = callback.data

        if callback_data == "create_invoice":
            await self._create_invoice_callback(callback, bot)
        elif callback_data.startswith("check_invoice_"):
            await self._check_payment_callback(callback, bot)

    async def _send_payment_request(self, message: Message, bot: Bot) -> None:
        """Отправка запроса на оплату"""
        builder = InlineKeyboardBuilder()
        button = InlineKeyboardButton(text="🛒 Оплатить", callback_data="create_invoice")
        builder.row(button)

        await message.answer(
            '📰 Чтобы пользоваться ботом необходимо оплатить подписку. \n\n'
            'Для оплаты доступа, используйте кнопку ниже.',
            parse_mode='HTML',
            reply_markup=builder.as_markup()
        )

    async def _create_invoice_callback(self, callback: CallbackQuery, bot: Bot) -> None:
        """Обработка создания счета"""
        await callback.answer()

        user_id = callback.from_user.id
        invoice = await self.payment_service.create_invoice_for_user(user_id)

        if "error" in invoice:
            await callback.message.answer("Ошибка при создании счета. Пожалуйста, попробуйте позже.")
            return

        builder = InlineKeyboardBuilder()
        button = InlineKeyboardButton(
            text="🔎 Проверить оплату",
            callback_data=f"check_invoice_{invoice['result']['uuid']}"
        )
        builder.row(button)

        await callback.message.answer(
            f"Ссылка на оплату: {invoice['result']['url']}",
            parse_mode='HTML',
            reply_markup=builder.as_markup()
        )

    async def _check_payment_callback(self, callback: CallbackQuery, bot: Bot) -> None:
        """Обработка проверки оплаты"""
        await callback.answer()

        invoice_uuid = callback.data.split("_")[2]
        payment_info = await self.payment_service.check_payment(invoice_uuid)

        if payment_info.get("result", {}).get("status") == "paid":
            user_id = callback.from_user.id

            # Добавляем пользователя в базу данных
            await self.user_repository.add_user(user_id)

            await callback.message.answer("✅ Оплачено! Теперь вы можете использовать все функции бота.")
        else:
            await callback.message.answer("❌ Счет не был оплачен. Пожалуйста, повторите позже.")

    def register_handlers(self, dp: Dispatcher) -> None:
        """Регистрация обработчиков"""
        # Обработка команды /start
        dp.message.register(self.cmd_start, Command("start"))

        # Обработка текстовых сообщений
        dp.message.register(self.handle_message)

        # Обработка callback
        dp.callback_query.register(self.handle_callback)

    async def cmd_start(self, message: Message) -> None:
        """Обработка команды /start"""
        builder = InlineKeyboardBuilder()
        button = InlineKeyboardButton(text="🛒 Оплатить", callback_data="create_invoice")
        builder.row(button)

        await message.answer(
            '📰 Чтобы пользоваться ботом необходимо оплатить подписку. \n\n'
            'Для оплаты доступа, используйте кнопку ниже.',
            parse_mode='HTML',
            reply_markup=builder.as_markup()
        )
