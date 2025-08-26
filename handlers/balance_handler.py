"""
Обработчик операций с балансом пользователя
"""
import logging
from typing import Dict, Any, Optional, Union

from aiogram.types import Message, CallbackQuery, InaccessibleMessage
from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from .base_handler import BaseHandler
from .error_handler import ErrorHandler
from utils.rate_limit_messages import RateLimitMessages


class BalanceHandler(BaseHandler):
    """
    Обработчик операций с балансом пользователя
    Предоставляет методы для отображения баланса и истории транзакций
    """

    def __init__(self, *args, **kwargs):
        """
        Инициализация обработчика баланса
        """
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)
        self.error_handler = ErrorHandler(*args, **kwargs)

    async def show_balance(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot) -> None:
        """
        Отображение баланса пользователя с использованием safe_execute
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
        """
        # Проверяем наличие пользователя перед извлечением ID
        if not message_or_callback.from_user or not message_or_callback.from_user.id:
            self.logger.warning("User information is missing in show_balance")
            return

        user_id = message_or_callback.from_user.id
            
        await self.safe_execute(
            user_id=user_id,
            operation="show_balance",
            func=self._show_balance_impl,
            message_or_callback=message_or_callback,
            bot=bot
        )

    async def _show_balance_impl(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot) -> None:
        """
        Реализация отображения баланса пользователя
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
        """
        if not message_or_callback.from_user or not message_or_callback.from_user.id:
            return

        user_id = message_or_callback.from_user.id
        
        # Определяем, является ли это сообщением или callback
        is_callback = isinstance(message_or_callback, CallbackQuery)
        message = message_or_callback.message if is_callback else message_or_callback

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

                # Проверяем, что сообщение доступно для редактирования
                if message and hasattr(message, 'edit_text') and not isinstance(message, InaccessibleMessage):
                    try:
                        if is_callback:
                            await message.edit_text(
                                balance_message,
                                reply_markup=builder.as_markup(),
                                parse_mode="HTML"
                            )
                        else:
                            await message.answer(
                                balance_message,
                                reply_markup=builder.as_markup(),
                                parse_mode="HTML"
                            )
                    except Exception as e:
                        self.logger.error(f"Error editing/answering message in show_balance: {e}")
                        # В случае ошибки пытаемся отправить новое сообщение
                        if hasattr(message_or_callback, 'answer'):
                            await message_or_callback.answer(
                                balance_message,
                                reply_markup=builder.as_markup(),
                                parse_mode="HTML"
                            )
                else:
                    # Если сообщение недоступно, отправляем новое
                    if hasattr(message_or_callback, 'answer'):
                        await message_or_callback.answer(
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

                # Проверяем, что сообщение доступно для редактирования
                if message and hasattr(message, 'edit_text') and not isinstance(message, InaccessibleMessage):
                    try:
                        if is_callback:
                            await message.edit_text(
                                "❌ <b>Не удалось получить баланс</b> ❌\n\n"
                                f"🔧 <i>Пожалуйста, попробуйте позже</i>\n\n"
                                f"💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                                reply_markup=builder.as_markup(),
                                parse_mode="HTML"
                            )
                        else:
                            await message.answer(
                                "❌ <b>Не удалось получить баланс</b> ❌\n\n"
                                f"🔧 <i>Пожалуйста, попробуйте позже</i>\n\n"
                                f"💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                                reply_markup=builder.as_markup(),
                                parse_mode="HTML"
                            )
                    except Exception as e:
                        self.logger.error(f"Error editing/answering message in show_balance error case: {e}")
                        # В случае ошибки пытаемся отправить новое сообщение
                        if hasattr(message_or_callback, 'answer'):
                            await message_or_callback.answer(
                                "❌ <b>Не удалось получить баланс</b> ❌\n\n"
                                f"🔧 <i>Пожалуйста, попробуйте позже</i>\n\n"
                                f"💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                                reply_markup=builder.as_markup(),
                                parse_mode="HTML"
                            )
                else:
                    # Если сообщение недоступно, отправляем новое
                    if hasattr(message_or_callback, 'answer'):
                        await message_or_callback.answer(
                            "❌ <b>Не удалось получить баланс</b> ❌\n\n"
                            f"🔧 <i>Пожалуйста, попробуйте позже</i>\n\n"
                            f"💡 <i>Если проблема сохраняется, обратитесь в поддержку</i>",
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )

        except Exception as e:
            self.logger.error(f"Error showing balance for user {user_id}: {e}")
            
            # Используем ErrorHandler для обработки ошибки
            await self.error_handler.show_error_with_suggestions(
                message_or_callback,
                self.error_handler.categorize_error(str(e)),
                {"user_id": user_id, "error": str(e)}
            )

    async def show_balance_history(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot) -> None:
        """
        Отображение истории баланса с использованием safe_execute
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
        """
        # Проверяем наличие пользователя перед извлечением ID
        if not message_or_callback.from_user or not message_or_callback.from_user.id:
            self.logger.warning("User information is missing in show_balance")
            return

        user_id = message_or_callback.from_user.id
            
        # Проверяем rate limit перед выполнением операции (20 операций в минуту)
        if not await self.check_rate_limit(user_id, "operation", 20, 60):
            self.logger.warning(f"Rate limit check failed for operation show_balance_history by user {user_id}")
            # Показываем пользователю сообщение о превышении лимита
            await self._show_rate_limit_message(message_or_callback, "operation")
            return
            
        await self.safe_execute(
            user_id=user_id,
            operation="show_balance_history",
            func=self._show_balance_history_impl,
            message_or_callback=message_or_callback,
            bot=bot
        )

    async def _show_balance_history_impl(self, message_or_callback: Union[Message, CallbackQuery], bot: Bot) -> None:
        """
        Реализация отображения истории баланса
        
        Args:
            message_or_callback: Сообщение или callback запрос
            bot: Экземпляр бота
        """
        if not message_or_callback.from_user or not message_or_callback.from_user.id:
            return

        user_id = message_or_callback.from_user.id
        
        # Определяем, является ли это сообщением или callback
        is_callback = isinstance(message_or_callback, CallbackQuery)
        message = message_or_callback.message if is_callback else message_or_callback

        try:
            # Получаем историю баланса
            history_data = await self.balance_service.get_user_balance_history(user_id, days=30)

            if not history_data or history_data.get("transactions_count", 0) == 0:
                builder = InlineKeyboardBuilder()
                builder.row(
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_balance")
                )

                # Проверяем, что сообщение доступно для редактирования
                if message and hasattr(message, 'edit_text') and not isinstance(message, InaccessibleMessage):
                    try:
                        if is_callback:
                            await message.edit_text(
                                "📊 <b>У вас пока нет истории транзакций</b> 📊\n\n"
                                f"🔍 <i>Ваши транзакции будут отображаться здесь</i>\n\n"
                                f"💡 <i>Совершите первую покупку, чтобы увидеть историю</i>",
                                reply_markup=builder.as_markup(),
                                parse_mode="HTML"
                            )
                        else:
                            await message.answer(
                                "📊 <b>У вас пока нет истории транзакций</b> 📊\n\n"
                                f"🔍 <i>Ваши транзакции будут отображаться здесь</i>\n\n"
                                f"💡 <i>Совершите первую покупку, чтобы увидеть историю</i>",
                                reply_markup=builder.as_markup(),
                                parse_mode="HTML"
                            )
                    except Exception as e:
                        self.logger.error(f"Error editing/answering message in show_balance_history no transactions: {e}")
                        # В случае ошибки пытаемся отправить новое сообщение
                        if hasattr(message_or_callback, 'answer'):
                            await message_or_callback.answer(
                                "📊 <b>У вас пока нет истории транзакций</b> 📊\n\n"
                                f"🔍 <i>Ваши транзакции будут отображаться здесь</i>\n\n"
                                f"💡 <i>Совершите первую покупку, чтобы увидеть историю</i>",
                                reply_markup=builder.as_markup(),
                                parse_mode="HTML"
                            )
                else:
                    # Если сообщение недоступно, отправляем новое
                    if hasattr(message_or_callback, 'answer'):
                        await message_or_callback.answer(
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

            # Рассчитываем изменение баланса
            balance_change = final_balance - initial_balance
            if balance_change > 0:
                change_text = f"+{balance_change:.2f} TON"
                change_icon = "📈"
            elif balance_change < 0:
                change_text = f"{balance_change:.2f} TON"
                change_icon = "📉"
            else:
                change_text = f"0.00 TON"
                change_icon = "➖"

            message_text = (
                f"📊 <b>История баланса за 30 дней</b> 📊\n\n"
                f"💰 <b>Начальный баланс:</b> {initial_balance:.2f} TON\n"
                f"💰 <b>Текущий баланс:</b> {final_balance:.2f} TON\n"
                f"{change_icon} <b>Изменение:</b> {change_text}\n"
                f"📈 <b>Всего транзакций:</b> {transactions_count}\n\n"
                f"🔄 <b>Последние операции:</b>\n\n"
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

                # Определяем иконку и знак операции на основе типа транзакции
                if transaction_type == "purchase":
                    icon = "🛒"
                    sign = "-"
                    operation_name = "Покупка"
                elif transaction_type == "refund":
                    icon = "💰"
                    sign = "+"
                    operation_name = "Возврат"
                elif transaction_type == "bonus":
                    icon = "🎁"
                    sign = "+"
                    operation_name = "Бонус"
                elif transaction_type == "recharge":
                    icon = "💳"
                    sign = "+"
                    operation_name = "Пополнение"
                elif transaction_type == "withdrawal":
                    icon = "💸"
                    sign = "-"
                    operation_name = "Списание"
                else:
                    # Для неизвестных типов пытаемся определить по сумме
                    if amount > 0:
                        icon = "💰"
                        sign = "+"
                        operation_name = "Пополнение"
                    else:
                        icon = "💸"
                        sign = "-"
                        operation_name = "Списание"

                # Определяем статус с более понятными названиями
                if status == "completed":
                    status_text = "✅ Выполнено"
                elif status == "failed":
                    status_text = "❌ Ошибка"
                elif status == "pending":
                    status_text = "⏳ В обработке"
                elif status == "cancelled":
                    status_text = "🚫 Отменено"
                else:
                    status_text = "⚪ Неизвестно"

                # Форматируем строку транзакции с улучшенным отображением
                message_text += f"{i}. {icon} <b>{operation_name}</b> {sign}{amount:.2f} TON\n"
                message_text += f"   {status_text} • {date_str}\n\n"

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_balance")
            )

            # Проверяем, что сообщение доступно для редактирования
            if message and hasattr(message, 'edit_text') and not isinstance(message, InaccessibleMessage):
                try:
                    if is_callback:
                        await message.edit_text(
                            message_text,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                    else:
                        await message.answer(
                            message_text,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
                except Exception as e:
                    self.logger.error(f"Error editing/answering message in show_balance_history success case: {e}")
                    # В случае ошибки пытаемся отправить новое сообщение
                    if hasattr(message_or_callback, 'answer'):
                        await message_or_callback.answer(
                            message_text,
                            reply_markup=builder.as_markup(),
                            parse_mode="HTML"
                        )
            else:
                # Если сообщение недоступно, отправляем новое
                if hasattr(message_or_callback, 'answer'):
                    await message_or_callback.answer(
                        message_text,
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )

        except Exception as e:
            self.logger.error(f"Error showing balance history for user {user_id}: {e}")
            
            # Используем ErrorHandler для обработки ошибки
            await self.error_handler.show_error_with_suggestions(
                message_or_callback,
                self.error_handler.categorize_error(str(e)),
                {"user_id": user_id, "error": str(e)}
            )

    async def handle_message(self, message: Message, bot: Bot) -> None:
        """
        Обработка текстовых сообщений (реализация абстрактного метода)
        
        Args:
            message: Текстовое сообщение
            bot: Экземпляр бота
        """
        # Обработка сообщений о балансе
        if message.text and "баланс" in message.text.lower():
            await self.show_balance(message, bot)
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
        if callback.data == "balance":
            await self.show_balance(callback, bot)
        elif callback.data == "balance_history":
            await self.show_balance_history(callback, bot)
        elif callback.data == "back_to_balance":
            await self.show_balance(callback, bot)
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
            # Проверяем наличие пользователя перед извлечением ID
            if not message_or_callback.from_user or not message_or_callback.from_user.id:
                self.logger.warning("User information is missing in _show_rate_limit_message")
                return

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