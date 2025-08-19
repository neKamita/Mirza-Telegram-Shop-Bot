"""
Обработчик операций с покупкой звезд
"""
import logging
from typing import Dict, Any, Optional, Union

from aiogram.types import Message, CallbackQuery
from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from .base_handler import BaseHandler
from .error_handler import ErrorHandler
from utils.rate_limit_messages import RateLimitMessages


class PurchaseHandler(BaseHandler):
    """
    Обработчик операций с покупкой звезд
    Предоставляет методы для покупки звезд через Heleket и с баланса
    """

    def __init__(self, *args, **kwargs):
        """
        Инициализация обработчика покупок
        """
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)
        self.error_handler = ErrorHandler(*args, **kwargs)

    def _format_payment_status(self, status: str) -> str:
        """Форматирование статуса оплаты с цветами и эмодзи"""
        status_formats = {
            'pending': '⏳ <b>статус: pending</b>',
            'paid': '✅ <b>статус: paid</b>',
            'failed': '❌ <b>статус: failed</b>',
            'expired': '⚪ <b>статус: expired</b>',
            'cancelled': '❌ <b>статус: cancelled</b>',
            'processing': '🔄 <b>статус: processing</b>',
            'unknown': '❓ <b>статус: unknown</b>'
        }
        return status_formats.get(status.lower(), '❓ <b>статус: unknown</b>')

    async def _show_buy_stars_menu(self, callback: CallbackQuery, bot: Bot, payment_type: str = "card") -> None:
        """
        Показать меню покупки звезд
        
        Args:
            callback: Callback запрос
            bot: Экземпляр бота
            payment_type: Тип оплаты ("card", "balance" или "fragment")
        """
        builder = InlineKeyboardBuilder()
        
        if payment_type == "card":
            # Меню для оплаты картой/кошельком
            builder.row(
                InlineKeyboardButton(text="⭐ 100 звезд", callback_data="buy_100"),
                InlineKeyboardButton(text="⭐ 250 звезд", callback_data="buy_250")
            )
            builder.row(
                InlineKeyboardButton(text="⭐ 500 звезд", callback_data="buy_500"),
                InlineKeyboardButton(text="⭐ 1000 звезд", callback_data="buy_1000")
            )
            title = "💳 <b>Покупка звезд картой/кошельком</b> 💳"
            description = "🔗 <i>Оплата через платежную систему Heleket</i>"
        elif payment_type == "balance":
            # Меню для оплаты с баланса
            builder.row(
                InlineKeyboardButton(text="⭐ 100 звезд", callback_data="buy_100_balance"),
                InlineKeyboardButton(text="⭐ 250 звезд", callback_data="buy_250_balance")
            )
            builder.row(
                InlineKeyboardButton(text="⭐ 500 звезд", callback_data="buy_500_balance"),
                InlineKeyboardButton(text="⭐ 1000 звезд", callback_data="buy_1000_balance")
            )
            title = "💰 <b>Покупка звезд с баланса</b> 💰"
            description = "💸 <i>Списание с вашего внутреннего баланса</i>"
        else:
            # Меню для оплаты через Fragment API
            builder.row(
                InlineKeyboardButton(text="⭐ 100 звезд", callback_data="buy_100_fragment"),
                InlineKeyboardButton(text="⭐ 250 звезд", callback_data="buy_250_fragment")
            )
            builder.row(
                InlineKeyboardButton(text="⭐ 500 звезд", callback_data="buy_500_fragment"),
                InlineKeyboardButton(text="⭐ 1000 звезд", callback_data="buy_1000_fragment")
            )
            title = "💎 <b>Покупка звезд через Fragment</b> 💎"
            description = "🚀 <i>Прямая покупка через Telegram Fragment API</i>"
        
        builder.row(
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
        )
        
        message_text = (
            f"{title}\n\n"
            f"{description}\n\n"
            f"🎯 <i>Выберите количество звезд:</i>\n\n"
            f"✨ <i>Каждая звезда имеет ценность!</i>"
        )
        
        try:
            await callback.message.edit_text(
                message_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception as e:
            self.logger.error(f"Error editing message in _show_buy_stars_menu: {e}")
            await callback.message.answer(
                message_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )

    async def buy_stars_preset(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, amount: int) -> None:
        """
        Покупка预设 пакетов звезд с использованием safe_execute
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            amount: Количество звезд для покупки
        """
        if isinstance(message_or_callback, CallbackQuery):
            user_id = message_or_callback.from_user.id
        else:
            user_id = message_or_callback.from_user.id
            
        await self.safe_execute(
            user_id=user_id,
            operation="buy_stars_preset",
            func=self._buy_stars_preset_impl,
            message_or_callback=message_or_callback,
            bot=bot,
            amount=amount
        )

    async def _buy_stars_preset_impl(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, amount: int) -> None:
        """
        Реализация покупки预设 пакетов звезд (только через баланс) - оптимизированная версия
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            amount: Количество звезд для покупки
        """
        if not message_or_callback.from_user or not message_or_callback.from_user.id:
            return

        user_id = message_or_callback.from_user.id
        is_callback = isinstance(message_or_callback, CallbackQuery)
        message = message_or_callback.message if is_callback else message_or_callback

        try:
            # Показываем быстрый индикатор загрузки
            if is_callback:
                await message_or_callback.answer("⏳ Обрабатываем покупку...", show_alert=False)
            
            # Используем новый сервис покупки звезд (только через баланс)
            purchase_result = await self.star_purchase_service.create_star_purchase(user_id, amount, purchase_type="balance")

            if purchase_result["status"] == "failed":
                error_msg = purchase_result.get("error", "Неизвестная ошибка")
                
                # Специальная обработка для недостаточного баланса
                if "Insufficient balance" in error_msg:
                    await self._handle_insufficient_balance_error(
                        message_or_callback, 
                        user_id, 
                        amount,
                        purchase_result.get("current_balance", 0),
                        purchase_result.get("required_amount", amount)
                    )
                    return
                
                # Используем ErrorHandler для обработки других ошибок
                error_type = await self.error_handler.handle_purchase_error(Exception(error_msg), {"user_id": user_id, "amount": amount})
                
                # Показываем ошибку с рекомендациями
                await self.error_handler.show_error_with_suggestions(
                    message_or_callback,
                    error_type,
                    {"user_id": user_id, "amount": amount}
                )
                return

            # Поскольку теперь покупка идет только через баланс, показываем успешное сообщение
            old_balance = purchase_result.get("old_balance", 0)
            new_balance = purchase_result.get("new_balance", 0)
            stars_count = purchase_result.get("stars_count", 0)

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="📊 История покупок", callback_data="balance_history"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
            )

            success_message = (
                f"🎉 <b>Покупка успешна!</b> 🎉\n\n"
                f"⭐ <b>Куплено звезд:</b> {stars_count}\n"
                f"💰 <b>Баланс до:</b> {old_balance:.2f} TON\n"
                f"💰 <b>Баланс после:</b> {new_balance:.2f} TON\n\n"
                f"🌟 <i>Спасибо за покупку!</i> 🌟\n\n"
                f"✨ Ваши звезды уже доступны для использования!"
            )

            if message:
                try:
                    if is_callback:
                        await message.edit_text(
                            success_message,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                    else:
                        await message.answer(
                            success_message,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                except Exception as e:
                    self.logger.error(f"Error editing/answering message in buy_stars_preset success case: {e}")
                    await message.answer(
                        success_message,
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )

        except Exception as e:
            self.logger.error(f"Error creating star purchase for user {user_id}: {e}")
            
            # Используем ErrorHandler для обработки ошибки
            error_type = await self.error_handler.handle_purchase_error(e, {"user_id": user_id, "amount": amount})
            
            # Показываем ошибку с рекомендациями
            await self.error_handler.show_error_with_suggestions(
                message_or_callback,
                error_type,
                {"user_id": user_id, "amount": amount, "error": str(e)}
            )

    async def buy_stars_custom(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, amount: int) -> None:
        """
        Покупка кастомного количества звезд с использованием safe_execute
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            amount: Количество звезд для покупки
        """
        if isinstance(message_or_callback, CallbackQuery):
            user_id = message_or_callback.from_user.id
        else:
            user_id = message_or_callback.from_user.id
            
        await self.safe_execute(
            user_id=user_id,
            operation="buy_stars_custom",
            func=self._buy_stars_custom_impl,
            message_or_callback=message_or_callback,
            bot=bot,
            amount=amount
        )

    async def _buy_stars_custom_impl(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, amount: int) -> None:
        """
        Реализация покупки кастомного количества звезд (только через баланс)
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            amount: Количество звезд для покупки
        """
        if not message_or_callback.from_user or not message_or_callback.from_user.id:
            return

        user_id = message_or_callback.from_user.id
        is_callback = isinstance(message_or_callback, CallbackQuery)
        message = message_or_callback.message if is_callback else message_or_callback

        try:
            # Используем новый сервис покупки звезд (только через баланс)
            purchase_result = await self.star_purchase_service.create_star_purchase(user_id, amount, purchase_type="balance")

            if purchase_result["status"] == "failed":
                error_msg = purchase_result.get("error", "Неизвестная ошибка")
                
                # Используем ErrorHandler для обработки ошибки
                error_type = await self.error_handler.handle_purchase_error(Exception(error_msg), {"user_id": user_id, "amount": amount})
                
                # Показываем ошибку с рекомендациями
                await self.error_handler.show_error_with_suggestions(
                    message_or_callback,
                    error_type,
                    {"user_id": user_id, "amount": amount}
                )
                return

            result = purchase_result.get("result", {})
            transaction_id = purchase_result.get("transaction_id")

            if not result or "uuid" not in result or "url" not in result:
                if message:
                    try:
                        if is_callback:
                            await message.edit_text("❌ Ошибка: некорректные данные от платежной системы")
                        else:
                            await message.answer("❌ Ошибка: некорректные данные от платежной системы")
                    except Exception as e:
                        self.logger.error(f"Error editing/answering message in buy_stars_custom data error case: {e}")
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

            # Добавляем статус оплаты в сообщение
            status_line = self._format_payment_status("pending")
            
            if message:
                try:
                    if is_callback:
                        await message.edit_text(
                            f"✅ <b>Создан счет на покупку {amount} звезд</b> ✅\n\n"
                            f"💳 <b>Ссылка на оплату:</b> {result['url']}\n\n"
                            f"📋 <b>ID счета:</b> {result['uuid']}\n"
                            f"🔢 <b>ID транзакции:</b> {transaction_id}\n"
                            f"{status_line}\n\n"
                            f"🔗 <i>Перейдите по ссылке для оплаты</i>\n"
                            f"⏰ <i>Счет действителен в течение 15 минут</i>",
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                    else:
                        await message.answer(
                            f"✅ <b>Создан счет на покупку {amount} звезд</b> ✅\n\n"
                            f"💳 <b>Ссылка на оплату:</b> {result['url']}\n\n"
                            f"📋 <b>ID счета:</b> {result['uuid']}\n"
                            f"🔢 <b>ID транзакции:</b> {transaction_id}\n"
                            f"{status_line}\n\n"
                            f"🔗 <i>Перейдите по ссылке для оплаты</i>\n"
                            f"⏰ <i>Счет действителен в течение 15 минут</i>",
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                except Exception as e:
                    self.logger.error(f"Error editing/answering message in buy_stars_custom success case: {e}")
                    # В случае ошибки редактирования, отправляем новое сообщение со статусом
                    status_line = self._format_payment_status("pending")
                    await message.answer(
                        f"✅ Создан счет на покупку {amount} звезд.\n\n"
                        f"💳 Ссылка на оплату: {result['url']}\n\n"
                        f"📋 ID счета: {result['uuid']}\n"
                        f"🔢 ID транзакции: {transaction_id}\n"
                        f"{status_line}",
                        reply_markup=builder.as_markup()
                    )

        except Exception as e:
            self.logger.error(f"Error creating custom star purchase for user {user_id}: {e}")
            
            # Используем ErrorHandler для обработки ошибки
            error_type = await self.error_handler.handle_purchase_error(e, {"user_id": user_id, "amount": amount})
            
            # Показываем ошибку с рекомендациями
            await self.error_handler.show_error_with_suggestions(
                message_or_callback,
                error_type,
                {"user_id": user_id, "amount": amount, "error": str(e)}
            )

    async def buy_stars_with_balance(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, amount: int) -> None:
        """
        Покупка звезд с баланса пользователя с использованием safe_execute
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            amount: Количество звезд для покупки
        """
        if isinstance(message_or_callback, CallbackQuery):
            user_id = message_or_callback.from_user.id
        else:
            user_id = message_or_callback.from_user.id
            
        await self.safe_execute(
            user_id=user_id,
            operation="buy_stars_with_balance",
            func=self._buy_stars_with_balance_impl,
            message_or_callback=message_or_callback,
            bot=bot,
            amount=amount
        )

    async def buy_stars_with_fragment(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, amount: int) -> None:
        """
        Покупка звезд через Fragment API с использованием safe_execute
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            amount: Количество звезд для покупки
        """
        if isinstance(message_or_callback, CallbackQuery):
            user_id = message_or_callback.from_user.id
        else:
            user_id = message_or_callback.from_user.id
            
        await self.safe_execute(
            user_id=user_id,
            operation="buy_stars_with_fragment",
            func=self._buy_stars_with_fragment_impl,
            message_or_callback=message_or_callback,
            bot=bot,
            amount=amount
        )

    async def _buy_stars_with_balance_impl(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, amount: int) -> None:
        """
        Реализация покупки звезд с баланса пользователя
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            amount: Количество звезд для покупки
        """
        if not message_or_callback.from_user or not message_or_callback.from_user.id:
            return

        user_id = message_or_callback.from_user.id
        is_callback = isinstance(message_or_callback, CallbackQuery)
        message = message_or_callback.message if is_callback else message_or_callback

        try:
            # Сохраняем текущее состояние для восстановления в случае ошибки
            original_message = message

            # Используем новый сервис покупки звезд с баланса
            purchase_result = await self.star_purchase_service.create_star_purchase(
                user_id=user_id,
                amount=amount,
                purchase_type="balance"
            )

            if purchase_result["status"] == "failed":
                error_msg = purchase_result.get("error", "Неизвестная ошибка")
                
                # Используем ErrorHandler для обработки ошибки
                error_type = await self.error_handler.handle_purchase_error(Exception(error_msg), {"user_id": user_id, "amount": amount})
                
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
                await self.error_handler.show_error_with_suggestions(
                    message_or_callback,
                    error_type,
                    error_context
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

            success_message = (
                f"🎉 <b>Покупка успешна!</b> 🎉\n\n"
                f"⭐ <b>Куплено звезд:</b> {stars_count}\n"
                f"💰 <b>Баланс до:</b> {old_balance:.2f} TON\n"
                f"💰 <b>Баланс после:</b> {new_balance:.2f} TON\n\n"
                f"🌟 <i>Спасибо за покупку!</i> 🌟\n\n"
                f"✨ Ваши звезды уже доступны для использования!"
            )

            if message:
                try:
                    if is_callback:
                        await message.edit_text(
                            success_message,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                    else:
                        await message.answer(
                            success_message,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                except Exception as e:
                    self.logger.error(f"Error editing/answering message in buy_stars_with_balance success case: {e}")
                    await message.answer(
                        success_message,
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )

        except Exception as e:
            self.logger.error(f"Error creating star purchase with balance for user {user_id}: {e}")
            
            # Используем ErrorHandler для обработки ошибки
            error_type = await self.error_handler.handle_purchase_error(e, {"user_id": user_id, "amount": amount})
            
            # Показываем ошибку с рекомендациями
            await self.error_handler.show_error_with_suggestions(
                message_or_callback,
                error_type,
                {"user_id": user_id, "amount": amount, "error": str(e)}
            )

    async def _buy_stars_with_fragment_impl(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, amount: int) -> None:
        """
        Реализация покупки звезд через Fragment API
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            amount: Количество звезд для покупки
        """
        if not message_or_callback.from_user or not message_or_callback.from_user.id:
            return

        user_id = message_or_callback.from_user.id
        is_callback = isinstance(message_or_callback, CallbackQuery)
        message = message_or_callback.message if is_callback else message_or_callback

        try:
            # Показываем быстрый индикатор загрузки
            if is_callback:
                await message_or_callback.answer("⏳ Обрабатываем покупку через Fragment...", show_alert=False)
            
            # Используем новый сервис покупки звезд через Fragment API
            purchase_result = await self.star_purchase_service.create_star_purchase(
                user_id=user_id,
                amount=amount,
                purchase_type="fragment"
            )

            if purchase_result["status"] == "failed":
                error_msg = purchase_result.get("error", "Неизвестная ошибка")
                
                # Используем ErrorHandler для обработки ошибки
                error_type = await self.error_handler.handle_purchase_error(Exception(error_msg), {"user_id": user_id, "amount": amount})
                
                # Показываем ошибку с рекомендациями
                await self.error_handler.show_error_with_suggestions(
                    message_or_callback,
                    error_type,
                    {"user_id": user_id, "amount": amount}
                )
                return

            # Показываем успешное сообщение
            stars_count = purchase_result.get("stars_count", 0)
            fragment_result = purchase_result.get("result", {})

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="📊 История покупок", callback_data="purchase_history"),
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_buy_stars")
            )

            success_message = (
                f"🎉 <b>Покупка через Fragment успешна!</b> 🎉\n\n"
                f"⭐ <b>Куплено звезд:</b> {stars_count}\n"
                f"🧾 <b>Статус:</b> {fragment_result.get('status', 'completed')}\n\n"
                f"🌟 <i>Спасибо за покупку!</i> 🌟\n\n"
                f"✨ Ваши звезды уже доступны для использования!"
            )

            if message:
                try:
                    if is_callback:
                        await message.edit_text(
                            success_message,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                    else:
                        await message.answer(
                            success_message,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                except Exception as e:
                    self.logger.error(f"Error editing/answering message in buy_stars_with_fragment success case: {e}")
                    await message.answer(
                        success_message,
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )

        except Exception as e:
            self.logger.error(f"Error creating star purchase with Fragment for user {user_id}: {e}")
            
            # Используем ErrorHandler для обработки ошибки
            error_type = await self.error_handler.handle_purchase_error(e, {"user_id": user_id, "amount": amount})
            
            # Показываем ошибку с рекомендациями
            await self.error_handler.show_error_with_suggestions(
                message_or_callback,
                error_type,
                {"user_id": user_id, "amount": amount, "error": str(e)}
            )

    async def handle_message(self, message: Message, bot: Bot) -> None:
        """
        Обработка текстовых сообщений (реализация абстрактного метода)
        
        Args:
            message: Текстовое сообщение
            bot: Экземпляр бота
        """
        # Обработка сообщений о покупке звезд
        if message.text and ("звезд" in message.text.lower() or "stars" in message.text.lower()):
            # Проверяем, является ли сообщение числом для покупки звезд
            if message.text.isdigit():
                amount = int(message.text)
                if 1 <= amount <= 10000:
                    await self.buy_stars_custom(message, bot, amount)
                else:
                    await message.answer("❌ Пожалуйста, введите количество звезд от 1 до 10000")
        else:
            await message.answer("❓ <b>Неизвестная команда</b> ❓\n\n"
                               "🔍 <i>Пожалуйста, используйте доступные команды</i>\n\n"
                               "💡 <i>Введите /start для возврата в меню</i>",
                               parse_mode="HTML")

    async def handle_callback(self, callback: CallbackQuery, bot: Bot) -> None:
        """
        Обработка callback запросов (реализация абстрактного метода)
        
        Args:
            callback: Callback запрос
            bot: Экземпляр бота
        """
        # Проверяем rate limit для всех callback операций
        user_id = callback.from_user.id
        if not await self.check_rate_limit(user_id, "operation", 20, 60):
            self.logger.warning(f"Rate limit exceeded for user {user_id} in purchase handler")
            await self._show_rate_limit_message(callback, "operation")
            return
            
        if callback.data == "buy_stars":
            # Показать меню покупок через карту/кошелек
            await self._show_buy_stars_menu(callback, bot, payment_type="card")
        elif callback.data == "buy_stars_balance":
            # Показать меню покупок с баланса
            await self._show_buy_stars_menu(callback, bot, payment_type="balance")
        elif callback.data == "buy_stars_fragment":
            # Показать меню покупок через Fragment API
            await self._show_buy_stars_menu(callback, bot, payment_type="fragment")
        elif callback.data in ["buy_100", "buy_250", "buy_500", "buy_1000"]:
            amount = int(callback.data.replace("buy_", ""))
            await self.buy_stars_preset(callback, bot, amount)
        elif callback.data in ["buy_100_balance", "buy_250_balance", "buy_500_balance", "buy_1000_balance"]:
            amount = int(callback.data.replace("buy_", "").replace("_balance", ""))
            await self.buy_stars_with_balance(callback, bot, amount)
        elif callback.data in ["buy_100_fragment", "buy_250_fragment", "buy_500_fragment", "buy_1000_fragment"]:
            amount = int(callback.data.replace("buy_", "").replace("_fragment", ""))
            await self.buy_stars_with_fragment(callback, bot, amount)
        elif callback.data.startswith("check_payment_"):
            payment_id = callback.data.replace("check_payment_", "")
            # Здесь может быть вызов метода проверки статуса платежа
            await callback.answer(f"🔍 Проверка статуса платежа {payment_id}")
        elif callback.data == "back_to_buy_stars":
            # Возврат к главному меню покупок
            from handlers.message_handler import MessageHandler
            await callback.message.edit_text(
                "⭐ <b>Покупка звезд</b> ⭐\n\n"
                "🎯 <i>Выберите способ оплаты:</i>\n\n"
                f"💳 <i>Картой/Кошельком - оплата через Heleket</i>\n"
                f"💰 <i>С баланса - списание со счета</i>\n"
                f"💎 <i>Через Fragment - прямая покупка</i>\n\n"
                f"✨ <i>Каждая звезда имеет ценность!</i>",
                reply_markup=InlineKeyboardBuilder().row(
                    InlineKeyboardButton(text="💳 Картой/Кошельком", callback_data="buy_stars"),
                    InlineKeyboardButton(text="💰 С баланса", callback_data="buy_stars_balance")
                ).row(
                    InlineKeyboardButton(text="💎 Через Fragment", callback_data="buy_stars_fragment")
                ).row(
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
                ).as_markup(),
                parse_mode="HTML"
            )
        else:
            await callback.answer("❓ <b>Неизвестное действие</b> ❓\n\n"
                               "🔍 <i>Пожалуйста, используйте доступные кнопки</i>\n\n"
                               "💡 <i>Введите /start для возврата в меню</i>",
                               show_alert=True)

    async def _show_rate_limit_message(self, message_or_callback: Union[Message, CallbackQuery], limit_type: str) -> None:
        """
        Показ сообщения о превышении rate limit пользователю
        
        Args:
            message_or_callback: Сообщение или callback запрос
            limit_type: Тип лимита
        """
        try:
            user_id = message_or_callback.from_user.id
            remaining_time = await self.get_rate_limit_remaining_time(user_id, limit_type)
            
            if isinstance(message_or_callback, Message):
                rate_limit_message = RateLimitMessages.get_rate_limit_message(limit_type, remaining_time, for_callback=False)
                await message_or_callback.answer(rate_limit_message, parse_mode="HTML")
            elif isinstance(message_or_callback, CallbackQuery):
                rate_limit_message = RateLimitMessages.get_rate_limit_message(limit_type, remaining_time, for_callback=True)
                await message_or_callback.answer(rate_limit_message, show_alert=True)
                
        except Exception as e:
            self.logger.error(f"Error showing rate limit message: {e}")

    async def _handle_insufficient_balance_error(self, message_or_callback, user_id: int, required_amount: int, current_balance: float, required_balance: float) -> None:
        """
        Специальная обработка ошибки недостаточного баланса
        
        Args:
            message_or_callback: Сообщение или callback запрос
            user_id: ID пользователя
            required_amount: Требуемое количество звезд
            current_balance: Текущий баланс пользователя
            required_balance: Требуемый баланс для покупки
        """
        from utils.message_templates import MessageTemplate
        
        missing_amount = max(0, required_balance - current_balance)
        
        # Создаем специальное сообщение
        insufficient_balance_message = MessageTemplate.get_insufficient_balance_message(
            current_balance=current_balance,
            required_amount=required_amount,
            missing_amount=missing_amount
        )
        
        # Создаем клавиатуру с действиями
        builder = InlineKeyboardBuilder()
        
        # Кнопка пополнения баланса на недостающую сумму (округляем вверх)
        recharge_amount = int(missing_amount) + 1 if missing_amount % 1 > 0 else int(missing_amount)
        builder.row(
            InlineKeyboardButton(
                text=f"💳 Пополнить на {recharge_amount} TON", 
                callback_data=f"recharge_{recharge_amount}"
            )
        )
        
        # Кнопки для покупки меньшего количества звезд
        if required_amount > 100:
            builder.row(
                InlineKeyboardButton(text="⭐ Купить 100 звезд", callback_data="buy_100"),
                InlineKeyboardButton(text="⭐ Купить 50 звезд", callback_data="buy_50")
            )
        elif required_amount > 50:
            builder.row(
                InlineKeyboardButton(text="⭐ Купить 50 звезд", callback_data="buy_50"),
                InlineKeyboardButton(text="⭐ Купить 25 звезд", callback_data="buy_25")
            )
        elif required_amount > 25:
            builder.row(
                InlineKeyboardButton(text="⭐ Купить 25 звезд", callback_data="buy_25"),
                InlineKeyboardButton(text="⭐ Купить 10 звезд", callback_data="buy_10")
            )
        
        # Кнопки навигации
        builder.row(
            InlineKeyboardButton(text="💰 Мой баланс", callback_data="balance"),
            InlineKeyboardButton(text="📊 История", callback_data="balance_history")
        )
        builder.row(
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
        )
        
        # Отправляем сообщение
        try:
            if isinstance(message_or_callback, CallbackQuery) and message_or_callback.message:
                await message_or_callback.message.edit_text(
                    insufficient_balance_message,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
            else:
                message = message_or_callback.message if isinstance(message_or_callback, CallbackQuery) else message_or_callback
                if message:
                    await message.answer(
                        insufficient_balance_message,
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
        except Exception as e:
            self.logger.error(f"Error showing insufficient balance message: {e}")
            # Fallback - простое текстовое сообщение
            fallback_message = (
                f"❌ Недостаточно средств на балансе\n\n"
                f"💰 Ваш баланс: {current_balance:.2f} TON\n"
                f"⭐ Нужно для покупки {required_amount} звезд: {required_balance:.2f} TON\n"
                f"❌ Не хватает: {missing_amount:.2f} TON\n\n"
                f"💡 Пополните баланс или выберите меньшее количество звезд"
            )
            if isinstance(message_or_callback, CallbackQuery):
                await message_or_callback.answer(fallback_message, show_alert=True)
            else:
                await message_or_callback.answer(fallback_message)