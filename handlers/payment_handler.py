"""
Обработчик операций с платежами пользователя
"""
import logging
from typing import Dict, Any, Optional, Union
from datetime import datetime

from aiogram.types import Message, CallbackQuery
from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from .base_handler import BaseHandler
from .error_handler import ErrorHandler
from utils.message_templates import MessageTemplate
from utils.rate_limit_messages import RateLimitMessages


class PaymentHandler(BaseHandler):
    """
    Обработчик операций с платежами пользователя
    Предоставляет методы для создания пополнений и проверки статуса платежей
    """

    def __init__(self, *args, **kwargs):
        """
        Инициализация обработчика платежей
        """
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)
        self.error_handler = ErrorHandler(*args, **kwargs)

    def _format_payment_status(self, status: str) -> str:
        """Форматирование статуса оплаты с использованием MessageTemplate"""
        return MessageTemplate._format_status(status)

    async def show_recharge_menu(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, amount: Optional[float] = None) -> None:
        """
        Показ меню для пополнения баланса с использованием safe_execute
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            amount: Сумма для пополнения (опционально)
        """
        if isinstance(message_or_callback, CallbackQuery):
            user_id = message_or_callback.from_user.id
        else:
            user_id = message_or_callback.from_user.id
            
        await self.safe_execute(
            user_id=user_id,
            operation="create_recharge",
            func=self._create_recharge_impl,
            message_or_callback=message_or_callback,
            bot=bot,
            amount=amount
        )

    # Старый метод _create_recharge_impl удален, так как теперь логика разделена:
    # - show_recharge_menu: показывает меню выбора сумм
    # - create_recharge: создает пополнение с указанной суммой

    async def check_recharge_status(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, payment_id: Optional[str] = None) -> None:
        """
        Проверка статуса пополнения с использованием safe_execute
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            payment_id: ID платежа (опционально)
        """
        if isinstance(message_or_callback, CallbackQuery):
            user_id = message_or_callback.from_user.id
        else:
            user_id = message_or_callback.from_user.id
            
        await self.safe_execute(
            user_id=user_id,
            operation="check_recharge_status",
            func=self._check_recharge_status_impl,
            message_or_callback=message_or_callback,
            bot=bot,
            payment_id=payment_id
        )

    async def _check_recharge_status_impl(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, payment_id: Optional[str] = None) -> None:
        """
        Реализация проверки статуса пополнения
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            payment_id: ID платежа (опционально)
        """
        if not message_or_callback.from_user or not message_or_callback.from_user.id:
            return

        user_id = message_or_callback.from_user.id
        is_callback = isinstance(message_or_callback, CallbackQuery)
        message = message_or_callback.message if is_callback else message_or_callback
        
        # Если payment_id не указан, извлекаем из callback
        if not payment_id and isinstance(message_or_callback, CallbackQuery):
            payment_id = message_or_callback.data.replace("check_recharge_", "")

        try:
            # Проверяем статус через сервис покупки звезд
            status_result = await self.star_purchase_service.check_recharge_status(payment_id)

            if status_result.get("status") == "failed":
                error_msg = status_result.get("error", "Неизвестная ошибка")
                
                # Используем ErrorHandler для обработки ошибки
                error_type = await self.error_handler.handle_purchase_error(Exception(error_msg), {"user_id": user_id, "payment_id": payment_id})
                
                # Показываем ошибку с рекомендациями
                await self.error_handler.show_error_with_suggestions(
                    message_or_callback,
                    error_type,
                    {"user_id": user_id, "payment_id": payment_id, "error": error_msg}
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
                # Для успешной оплаты не показываем кнопку обновления
                show_refresh_button = False
            elif payment_status == "pending":
                status_message = "⏳ Оплата в процессе..."
                status_color = "⏳"
                show_refresh_button = True
                # Планируем автоматическое обновление через 10 секунд
                import asyncio
                await asyncio.sleep(10)
                await self.check_recharge_status(message_or_callback, bot, payment_id)
                return
            elif payment_status == "failed":
                status_message = "❌ Оплата не удалась"
                status_color = "❌"
                show_refresh_button = True
            elif payment_status == "cancelled":
                status_message = "❌ Оплата отменена"
                status_color = "❌"
                show_refresh_button = True
            else:
                status_message = "❓ Неизвестный статус"
                status_color = "❓"
                show_refresh_button = True

            builder = InlineKeyboardBuilder()
            if show_refresh_button:
                builder.row(
                    InlineKeyboardButton(text="🔄 Обновить", callback_data=f"check_recharge_{payment_id}"),
                    InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cancel_recharge_{payment_id}")
                )
            else:
                builder.row(
                    InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cancel_recharge_{payment_id}")
                )

            if message:
                try:
                    # Получаем текущий текст сообщения
                    existing_text = message.text or ""
                    
                    # Находим и заменяем строку со статусом
                    lines = existing_text.split('\n')
                    new_lines = []
                    status_found = False
                    
                    for line in lines:
                        if 'статус:' in line.lower():
                            # Заменяем строку статуса с добавлением времени
                            current_time = datetime.now().strftime("%H:%M:%S")
                            new_status = f"⏳ <b>статус: pending ({current_time})</b>"
                            new_lines.append(new_status)
                            status_found = True
                        else:
                            new_lines.append(line)
                    
                    # Если строка статуса не найдена, добавляем ее
                    if not status_found:
                        # Находим позицию для вставки статуса (после ID транзакции)
                        for i, line in enumerate(new_lines):
                            if 'ID транзакции:' in line or 'ID платежа:' in line:
                                new_lines.insert(i + 1, "")
                                current_time = datetime.now().strftime("%H:%M:%S")
                                new_status = f"⏳ <b>статус: pending ({current_time})</b>"
                                new_lines.insert(i + 2, new_status)
                                break
                        else:
                            # Если не нашли, добавляем в конец
                            new_lines.append("")
                            current_time = datetime.now().strftime("%H:%M:%S")
                            new_status = f"⏳ <b>статус: pending ({current_time})</b>"
                            new_lines.append(new_status)
                    
                    updated_text = '\n'.join(new_lines)
                    
                    if is_callback:
                        await message.edit_text(
                            updated_text,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                    else:
                        await message.answer(
                            updated_text,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                except Exception as e:
                    self.logger.error(f"Error editing/answering message in check_recharge_status success case: {e}")
                    # В случае ошибки редактирования, ничего не отправляем
                    pass

        except Exception as e:
            self.logger.error(f"Error checking recharge status for {payment_id}: {e}")
            
            # Используем ErrorHandler для обработки ошибки
            error_type = await self.error_handler.handle_purchase_error(e, {"user_id": user_id, "payment_id": payment_id})
            
            # Показываем ошибку с рекомендациями
            await self.error_handler.show_error_with_suggestions(
                message_or_callback,
                error_type,
                {"user_id": user_id, "payment_id": payment_id, "error": str(e)}
            )

    async def create_recharge(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, amount: float) -> None:
        """
        Создание пополнения с указанной суммой с использованием safe_execute
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            amount: Сумма для пополнения
        """
        if isinstance(message_or_callback, CallbackQuery):
            user_id = message_or_callback.from_user.id
        else:
            user_id = message_or_callback.from_user.id
            
        await self.safe_execute(
            user_id=user_id,
            operation="create_recharge",
            func=self._create_recharge_impl,
            message_or_callback=message_or_callback,
            bot=bot,
            amount=amount
        )

    async def _create_recharge_impl(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot, amount: float) -> None:
        """
        Реализация создания пополнения с указанной суммой
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
            amount: Сумма для пополнения
        """
        if not message_or_callback.from_user or not message_or_callback.from_user.id:
            return

        user_id = message_or_callback.from_user.id
        is_callback = isinstance(message_or_callback, CallbackQuery)
        message = message_or_callback.message if is_callback else message_or_callback

        try:
            # Используем сервис покупки звезд для создания пополнения
            recharge_result = await self.star_purchase_service.create_recharge(user_id, amount)

            if recharge_result["status"] == "failed":
                error_msg = recharge_result.get("error", "Неизвестная ошибка")
                
                # Используем ErrorHandler для обработки ошибки
                error_type = await self.error_handler.handle_purchase_error(Exception(error_msg), {"user_id": user_id, "amount": amount})
                
                # Показываем ошибку с рекомендациями
                await self.error_handler.show_error_with_suggestions(
                    message_or_callback,
                    error_type,
                    {"user_id": user_id, "amount": amount, "error": error_msg}
                )
                return

            result = recharge_result.get("result", {})
            transaction_id = recharge_result.get("transaction_id")

            if not result or "uuid" not in result or "url" not in result:
                if message:
                    try:
                        if is_callback:
                            await message.edit_text("❌ Ошибка: некорректные данные от платежной системы")
                        else:
                            await message.answer("❌ Ошибка: некорректные данные от платежной системы")
                    except Exception as e:
                        self.logger.error(f"Error editing/answering message in handle_recharge_amount data error case: {e}")
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
                    callback_data=f"cancel_recharge_{result['uuid']}"
                )
            )

            if message:
                try:
                    # Добавляем статус оплаты в сообщение
                    status_line = self._format_payment_status("pending")
                    
                    if is_callback:
                        await message.edit_text(
                            f"✅ <b>Создан счет на пополнение баланса на {amount} TON</b> ✅\n\n"
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
                            f"✅ <b>Создан счет на пополнение баланса на {amount} TON</b> ✅\n\n"
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
                    self.logger.error(f"Error editing/answering message in handle_recharge_amount success case: {e}")
                    # В случае ошибки редактирования, отправляем новое сообщение со статусом
                    status_line = self._format_payment_status("pending")
                    await message.answer(
                        f"✅ Создан счет на пополнение баланса на {amount} TON.\n\n"
                        f"💳 Ссылка на оплату: {result['url']}\n\n"
                        f"📋 ID счета: {result['uuid']}\n"
                        f"🔢 ID транзакции: {transaction_id}\n"
                        f"{status_line}",
                        reply_markup=builder.as_markup()
                    )

        except Exception as e:
            self.logger.error(f"Error creating recharge for user {user_id}: {e}")
            
            # Используем ErrorHandler для обработки ошибки
            error_type = await self.error_handler.handle_purchase_error(e, {"user_id": user_id, "amount": amount})
            
            # Показываем ошибку с рекомендациями
            await self.error_handler.show_error_with_suggestions(
                message_or_callback,
                error_type,
                {"user_id": user_id, "amount": amount, "error": str(e)}
            )

    async def cancel_specific_recharge(self, callback: CallbackQuery, bot: Bot, payment_id: str) -> None:
        """
        Отмена конкретного пополнения с использованием safe_execute
        
        Args:
            callback: Callback запрос
            bot: Экземпляр бота
            payment_id: UUID платежа для отмены
        """
        user_id = callback.from_user.id
        
        await self.safe_execute(
            user_id=user_id,
            operation="cancel_recharge",
            func=self._cancel_specific_recharge_impl,
            callback=callback,
            bot=bot,
            payment_id=payment_id
        )

    async def _cancel_specific_recharge_impl(self, callback: CallbackQuery, bot: Bot, payment_id: str) -> None:
        """
        Реализация отмены конкретного пополнения
        
        Args:
            callback: Callback запрос
            bot: Экземпляр бота
            payment_id: UUID платежа для отмены
        """
        if not callback.from_user or not callback.from_user.id:
            return

        user_id = callback.from_user.id

        try:
            # Отменяем конкретный инвойс
            success = await self.star_purchase_service.cancel_specific_recharge(user_id, payment_id)
            
            if success:
                self.logger.info(f"Successfully cancelled recharge {payment_id} for user {user_id}")
                
                # Возвращаемся к меню выбора сумм для пополнения
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
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
                )
                
                try:
                    if callback.message:
                        await callback.message.edit_text(
                            "❌ <b>Инвойс отменен</b> ❌\n\n"
                            "💳 <b>Выберите сумму для пополнения</b> 💳\n\n"
                            "🎯 <i>Доступные варианты:</i>\n\n"
                            f"💰 <i>10 TON - Минимальное пополнение</i>\n"
                            f"💰 <i>50 TON - Стандартное пополнение</i>\n"
                            f"💰 <i>100 TON - Комфортное пополнение</i>\n"
                            f"💰 <i>500 TON - Максимальное пополнение</i>\n\n"
                            f"✨ <i>Выберите удобную для вас сумму</i>",
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                    else:
                        await callback.answer("❌ Инвойс отменен", show_alert=True)
                except Exception as e:
                    self.logger.error(f"Error editing message after cancelling recharge: {e}")
                    await callback.answer("❌ Инвойс отменен", show_alert=True)
            else:
                # Инвойс не удалось отменить (возможно, уже не pending)
                await callback.answer("ℹ️ Инвойс уже обработан или не найден", show_alert=True)

        except Exception as e:
            self.logger.error(f"Error cancelling specific recharge {payment_id} for user {user_id}: {e}")
            
            # Используем ErrorHandler для обработки ошибки
            error_type = await self.error_handler.handle_purchase_error(e, {"user_id": user_id, "payment_id": payment_id})
            
            # Показываем ошибку с рекомендациями
            await self.error_handler.show_error_with_suggestions(
                callback,
                error_type,
                {"user_id": user_id, "payment_id": payment_id, "error": str(e)}
            )

    async def handle_message(self, message: Message, bot: Bot) -> None:
        """
        Обработка текстовых сообщений (реализация абстрактного метода)
        
        Args:
            message: Текстовое сообщение
            bot: Экземпляр бота
        """
        # Обработка сообщений о пополнении
        if message.text and ("пополнение" in message.text.lower() or "recharge" in message.text.lower()):
            await self.create_recharge(message, bot)
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
            self.logger.warning(f"Rate limit exceeded for user {user_id} in payment handler")
            await self._show_rate_limit_message(callback, "operation")
            return
            
        if callback.data == "recharge":
            # Показываем меню выбора сумм для пополнения
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
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
            )
            
            try:
                if callback.message:
                    await callback.message.edit_text(
                        "💳 <b>Выберите сумму для пополнения</b> 💳\n\n"
                        "🎯 <i>Доступные варианты:</i>\n\n"
                        f"💰 <i>10 TON - Минимальное пополнение</i>\n"
                        f"💰 <i>50 TON - Стандартное пополнение</i>\n"
                        f"💰 <i>100 TON - Комфортное пополнение</i>\n"
                        f"💰 <i>500 TON - Максимальное пополнение</i>\n\n"
                        f"✨ <i>Выберите удобную для вас сумму</i>",
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
                else:
                    await callback.answer("❌ <b>Ошибка: сообщение не найдено</b> ❓", show_alert=True)
            except Exception as e:
                self.logger.error(f"Error showing recharge menu: {e}")
                await callback.answer("❌ <b>Ошибка при отображении меню</b> ❓", show_alert=True)
        elif callback.data.startswith("check_recharge_"):
            payment_id = callback.data.replace("check_recharge_", "")
            await self.check_recharge_status(callback, bot, payment_id)
        elif callback.data.startswith("cancel_recharge_"):
            payment_id = callback.data.replace("cancel_recharge_", "")
            await self.cancel_specific_recharge(callback, bot, payment_id)
        elif callback.data in ["recharge_10", "recharge_50", "recharge_100", "recharge_500"]:
            amount = float(callback.data.replace("recharge_", ""))
            await self.create_recharge(callback, bot, amount)
        elif callback.data == "back_to_recharge":
            await self.create_recharge(callback, bot)
        elif callback.data == "recharge_custom":
            # Отменяем все pending пополнения пользователя при возврате в меню
            try:
                cancelled_count = await self.star_purchase_service.cancel_pending_recharges(user_id)
                if cancelled_count > 0:
                    self.logger.info(f"Cancelled {cancelled_count} pending recharge(s) for user {user_id} on back button")
            except Exception as e:
                self.logger.error(f"Error cancelling pending recharges for user {user_id}: {e}")
            
            # Возвращаемся к меню выбора сумм для пополнения
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
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")
            )
            
            try:
                if callback.message:
                    await callback.message.edit_text(
                        "💳 <b>Выберите сумму для пополнения</b> 💳\n\n"
                        "🎯 <i>Доступные варианты:</i>\n\n"
                        f"💰 <i>10 TON - Минимальное пополнение</i>\n"
                        f"💰 <i>50 TON - Стандартное пополнение</i>\n"
                        f"💰 <i>100 TON - Комфортное пополнение</i>\n"
                        f"💰 <i>500 TON - Максимальное пополнение</i>\n\n"
                        f"✨ <i>Выберите удобную для вас сумму</i>",
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
                else:
                    await callback.answer("❌ <b>Ошибка: сообщение не найдено</b> ❓", show_alert=True)
            except Exception as e:
                self.logger.error(f"Error showing recharge menu from recharge_custom: {e}")
                await callback.answer("❌ <b>Ошибка при отображении меню</b> ❓", show_alert=True)
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