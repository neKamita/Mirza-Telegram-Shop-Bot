"""
Комплексные unit-тесты для MessageHandler - центрального диспетчера сообщений Telegram бота

Тестирование всех функций обработки сообщений и callback-запросов:
- Обработка текстовых команд (/start, /balance, /payment, /purchase, /help)
- Обработка числовых команд для покупки звезд
- Обработка callback запросов всех типов
- Валидация входных данных и rate limiting
- Делегирование обработки специализированным обработчикам
- Обработка ошибок и исключительных ситуаций
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, MagicMock, patch
import logging
from typing import Dict, Any, Optional

from aiogram.types import Message, CallbackQuery, User, Chat, InaccessibleMessage
from aiogram import Bot, Dispatcher
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.message_handler import MessageHandler
from handlers.base_handler import BaseHandler
from handlers.error_handler import ErrorHandler
from handlers.balance_handler import BalanceHandler
from handlers.payment_handler import PaymentHandler
from handlers.purchase_handler import PurchaseHandler
from utils.message_templates import MessageTemplate
from utils.rate_limit_messages import RateLimitMessages


class TestMessageHandler:
    """Комплексные тесты для MessageHandler"""

    @pytest.fixture
    def mock_services(self):
        """Фикстура для создания моков сервисов"""
        return {
            'user_repository': Mock(),
            'payment_service': Mock(),
            'balance_service': Mock(),
            'star_purchase_service': Mock(),
            'session_cache': Mock(),
            'rate_limit_cache': Mock(),
            'payment_cache': Mock()
        }

    @pytest.fixture
    def message_handler(self, mock_services):
        """Фикстура для создания экземпляра MessageHandler с моками"""
        # Создаем моки для всех зависимостей BaseHandler
        handler = MessageHandler(
            user_repository=mock_services['user_repository'],
            payment_service=mock_services['payment_service'],
            balance_service=mock_services['balance_service'],
            star_purchase_service=mock_services['star_purchase_service'],
            session_cache=mock_services['session_cache'],
            rate_limit_cache=mock_services['rate_limit_cache'],
            payment_cache=mock_services['payment_cache']
        )

        # Дополнительные моки для базового функционала
        handler.logger = Mock()
        handler.check_rate_limit = AsyncMock(return_value=True)
        handler.get_rate_limit_remaining_time = AsyncMock(return_value=30)
        handler.validate_user = AsyncMock(return_value=True)
        
        # Моки для специализированных обработчиков
        handler.error_handler = Mock(spec=ErrorHandler)
        handler.balance_handler = Mock(spec=BalanceHandler)
        handler.payment_handler = Mock(spec=PaymentHandler)
        handler.purchase_handler = Mock(spec=PurchaseHandler)
        
        # Настраиваем моки методов обработчиков
        handler.balance_handler.show_balance = AsyncMock()
        handler.balance_handler.show_balance_history = AsyncMock()
        handler.balance_handler.handle_callback = AsyncMock()
        
        handler.payment_handler.create_recharge = AsyncMock()
        handler.payment_handler.check_recharge_status = AsyncMock()
        handler.payment_handler.cancel_specific_recharge = AsyncMock()
        handler.payment_handler.show_recharge_menu = AsyncMock()
        handler.payment_handler.handle_callback = AsyncMock()
        
        handler.purchase_handler.buy_stars_preset = AsyncMock()
        handler.purchase_handler.buy_stars_with_balance = AsyncMock()
        handler.purchase_handler.buy_stars_custom = AsyncMock()
        handler.purchase_handler.handle_callback = AsyncMock()
        
        handler.error_handler.show_error_with_suggestions = AsyncMock()
        handler.error_handler.handle_error_action = AsyncMock()
        handler.error_handler.categorize_error = Mock(return_value="UNKNOWN_ERROR")
        
        return handler

    @pytest.fixture
    def mock_message(self):
        """Фикстура для создания мока сообщения"""
        message = Mock(spec=Message)
        message.from_user = Mock(spec=User)
        message.from_user.id = 12345
        message.text = "/start"
        message.answer = AsyncMock()
        message.edit_text = AsyncMock()
        return message

    @pytest.fixture
    def mock_callback(self):
        """Фикстура для создания мока callback"""
        callback = Mock(spec=CallbackQuery)
        callback.from_user = Mock(spec=User)
        callback.from_user.id = 12345
        callback.data = "balance"
        callback.answer = AsyncMock()
        callback.message = Mock(spec=Message)
        callback.message.edit_text = AsyncMock()
        callback.message.answer = AsyncMock()
        return callback

    @pytest.fixture
    def mock_bot(self):
        """Фикстура для создания мока бота"""
        return Mock(spec=Bot)

    @pytest.fixture
    def mock_dispatcher(self):
        """Фикстура для создания мока диспетчера"""
        dispatcher = Mock(spec=Dispatcher)
        dispatcher.message = Mock()
        dispatcher.callback_query = Mock()
        return dispatcher

    # Тесты обработки сообщений
    @pytest.mark.asyncio
    async def test_handle_message_no_text(self, message_handler, mock_message, mock_bot):
        """Тест обработки сообщения без текста"""
        mock_message.text = None
        
        await message_handler.handle_message(mock_message, mock_bot)
        
        mock_message.answer.assert_called_once_with(
            MessageTemplate.get_unknown_command(), parse_mode="HTML"
        )

    @pytest.mark.asyncio
    async def test_handle_message_validation_failed(self, message_handler, mock_message, mock_bot):
        """Тест обработки сообщения с проваленной валидацией"""
        message_handler._validate_input = AsyncMock(return_value=False)
        
        await message_handler.handle_message(mock_message, mock_bot)
        
        message_handler._validate_input.assert_called_once_with(mock_message)
        mock_message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_start_command(self, message_handler, mock_message, mock_bot):
        """Тест обработки команды /start"""
        mock_message.text = "/start"
        
        await message_handler.handle_message(mock_message, mock_bot)
        
        # Проверяем, что отправлено приветственное сообщение (не вызывается show_balance)
        mock_message.answer.assert_called_once()
        args, kwargs = mock_message.answer.call_args
        assert "Добро пожаловать" in kwargs.get('text', '') or "Добро пожаловать" in (args[0] if args else '')
        assert kwargs.get('parse_mode') == "HTML"
        message_handler.balance_handler.show_balance.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_balance_command(self, message_handler, mock_message, mock_bot):
        """Тест обработки команды /balance"""
        mock_message.text = "/balance"
        
        await message_handler.handle_message(mock_message, mock_bot)
        
        # Проверяем, что вызван соответствующий обработчик
        message_handler.balance_handler.show_balance.assert_called_once_with(mock_message, mock_bot)

    @pytest.mark.asyncio
    async def test_handle_message_payment_command(self, message_handler, mock_message, mock_bot):
        """Тест обработки команды /payment"""
        mock_message.text = "/payment"
        
        await message_handler.handle_message(mock_message, mock_bot)
        
        # Проверяем, что вызван соответствующий обработчик
        message_handler.payment_handler.show_recharge_menu.assert_called_once_with(mock_message, mock_bot)

    @pytest.mark.asyncio
    async def test_handle_message_purchase_command(self, message_handler, mock_message, mock_bot):
        """Тест обработки команды /purchase"""
        mock_message.text = "/purchase"
        
        await message_handler.handle_message(mock_message, mock_bot)
        
        # Проверяем, что отправлено сообщение с меню покупок
        mock_message.answer.assert_called_once()
        args, kwargs = mock_message.answer.call_args
        assert "Покупка звезд" in kwargs.get('text', '') or "Покупка звезд" in (args[0] if args else '')

    @pytest.mark.asyncio
    async def test_handle_message_help_command(self, message_handler, mock_message, mock_bot):
        """Тест обработки команды /help"""
        mock_message.text = "/help"
        
        await message_handler.handle_message(mock_message, mock_bot)
        
        # Проверяем, что отправлено сообщение помощи
        mock_message.answer.assert_called_once()
        args, kwargs = mock_message.answer.call_args
        assert "Помощь" in kwargs.get('text', '') or "Помощь" in (args[0] if args else '')

    @pytest.mark.asyncio
    async def test_handle_message_numeric_command_valid(self, message_handler, mock_message, mock_bot):
        """Тест обработки валидной числовой команды"""
        mock_message.text = "100"
        
        await message_handler.handle_message(mock_message, mock_bot)
        
        message_handler.purchase_handler.buy_stars_custom.assert_called_once_with(
            mock_message, mock_bot, 100
        )

    @pytest.mark.asyncio
    async def test_handle_message_numeric_command_too_small(self, message_handler, mock_message, mock_bot):
        """Тест обработки слишком маленькой числовой команды"""
        mock_message.text = "0"
        
        await message_handler.handle_message(mock_message, mock_bot)
        
        mock_message.answer.assert_called_once()
        message_handler.purchase_handler.buy_stars_custom.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_numeric_command_too_large(self, message_handler, mock_message, mock_bot):
        """Тест обработки слишком большой числовой команды"""
        mock_message.text = "10001"
        
        await message_handler.handle_message(mock_message, mock_bot)
        
        mock_message.answer.assert_called_once()
        message_handler.purchase_handler.buy_stars_custom.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_unknown_command(self, message_handler, mock_message, mock_bot):
        """Тест обработки неизвестной команды"""
        mock_message.text = "unknown_command"
        
        await message_handler.handle_message(mock_message, mock_bot)
        
        # Проверяем, что отправлено сообщение о неизвестной команде
        mock_message.answer.assert_called_once_with(MessageTemplate.get_unknown_command(), parse_mode="HTML")

    # Тесты обработки callback запросов
    @pytest.mark.asyncio
    async def test_handle_callback_no_data(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback без данных"""
        mock_callback.data = None
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        mock_callback.answer.assert_called_once_with(
            MessageTemplate.get_unknown_callback(), show_alert=True
        )

    @pytest.mark.asyncio
    async def test_handle_callback_validation_failed(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback с проваленной валидацией"""
        message_handler._validate_input = AsyncMock(return_value=False)
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler._validate_input.assert_called_once_with(mock_callback)
        mock_callback.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_callback_check_recharge(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback проверки пополнения"""
        mock_callback.data = "check_recharge_test_123"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler.payment_handler.check_recharge_status.assert_called_once_with(
            mock_callback, mock_bot, "test_123"
        )

    @pytest.mark.asyncio
    async def test_handle_callback_check_payment(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback проверки платежа"""
        mock_callback.data = "check_payment_test_456"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler.payment_handler.check_recharge_status.assert_called_once_with(
            mock_callback, mock_bot, "test_456"
        )

    @pytest.mark.asyncio
    async def test_handle_callback_cancel_recharge(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback отмены пополнения"""
        mock_callback.data = "cancel_recharge_test_789"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler.payment_handler.cancel_specific_recharge.assert_called_once_with(
            mock_callback, mock_bot, "test_789"
        )

    @pytest.mark.asyncio
    async def test_handle_callback_buy_preset(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback покупки пресета"""
        mock_callback.data = "buy_100"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler.purchase_handler.buy_stars_preset.assert_called_once_with(
            mock_callback, mock_bot, 100
        )

    @pytest.mark.asyncio
    async def test_handle_callback_buy_with_balance(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback покупки с баланса"""
        mock_callback.data = "buy_250_balance"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler.purchase_handler.buy_stars_with_balance.assert_called_once_with(
            mock_callback, mock_bot, 250
        )

    @pytest.mark.asyncio
    async def test_handle_callback_recharge_amount(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback пополнения на сумму"""
        mock_callback.data = "recharge_50"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler.payment_handler.create_recharge.assert_called_once_with(
            mock_callback, mock_bot, 50.0
        )

    @pytest.mark.asyncio
    async def test_handle_callback_back_to_main(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback возврата в главное меню"""
        mock_callback.data = "back_to_main"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        # Проверяем, что сообщение было отредактировано с приветственным текстом
        mock_callback.message.edit_text.assert_called_once()
        args, kwargs = mock_callback.message.edit_text.call_args
        assert "Добро пожаловать" in kwargs.get('text', '') or "Добро пожаловать" in (args[0] if args else '')
        assert kwargs.get('parse_mode') == "HTML"

    @pytest.mark.asyncio
    async def test_handle_callback_help(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback помощи"""
        mock_callback.data = "help"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        # Проверяем, что сообщение было отредактировано с текстом помощи
        mock_callback.message.edit_text.assert_called_once()
        args, kwargs = mock_callback.message.edit_text.call_args
        assert "Помощь" in kwargs.get('text', '') or "Помощь" in (args[0] if args else '')
        assert kwargs.get('parse_mode') == "HTML"

    @pytest.mark.asyncio
    async def test_handle_callback_error_action(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback действия ошибки"""
        mock_callback.data = "error_action_test"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler.error_handler.handle_error_action.assert_called_once_with(
            mock_callback, mock_bot
        )

    @pytest.mark.asyncio
    async def test_handle_callback_balance(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback баланса"""
        mock_callback.data = "balance"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler.balance_handler.handle_callback.assert_called_once_with(
            mock_callback, mock_bot
        )

    @pytest.mark.asyncio
    async def test_handle_callback_balance_history(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback истории баланса"""
        mock_callback.data = "balance_history"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler.balance_handler.handle_callback.assert_called_once_with(
            mock_callback, mock_bot
        )

    @pytest.mark.asyncio
    async def test_handle_callback_buy_stars(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback покупки звезд"""
        mock_callback.data = "buy_stars"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler.purchase_handler.handle_callback.assert_called_once_with(
            mock_callback, mock_bot
        )

    @pytest.mark.asyncio
    async def test_handle_callback_recharge(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback пополнения"""
        mock_callback.data = "recharge"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler.payment_handler.handle_callback.assert_called_once_with(
            mock_callback, mock_bot
        )

    @pytest.mark.asyncio
    async def test_handle_callback_back_to_balance(self, message_handler, mock_callback, mock_bot):
        """Тест обработки callback возврата к балансу"""
        mock_callback.data = "back_to_balance"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        message_handler.balance_handler.show_balance.assert_called_once_with(
            mock_callback, mock_bot
        )

    @pytest.mark.asyncio
    async def test_handle_callback_unknown(self, message_handler, mock_callback, mock_bot):
        """Тест обработки неизвестного callback"""
        mock_callback.data = "unknown_callback_data"
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        # Проверяем, что callback был обработан с сообщением об ошибке
        mock_callback.answer.assert_called_once()
        args, kwargs = mock_callback.answer.call_args
        assert kwargs.get('show_alert') is True
        # Проверяем, что текст содержит сообщение об ошибке
        assert "Неизвестное действие" in args[0] or "Unknown" in args[0]

    @pytest.mark.asyncio
    async def test_handle_callback_exception(self, message_handler, mock_callback, mock_bot):
        """Тест обработки исключения в callback"""
        mock_callback.data = "balance"  # Используем существующий callback
        # Мокаем успешную валидацию, но вызываем исключение при обработке баланса
        message_handler._validate_input = AsyncMock(return_value=True)
        message_handler.balance_handler.handle_callback = AsyncMock(side_effect=Exception("Test error"))
        
        await message_handler.handle_callback(mock_callback, mock_bot)
        
        # Проверяем, что ошибка обработана через error_handler
        message_handler.error_handler.show_error_with_suggestions.assert_called_once()

    # Тесты регистрации обработчиков
    def test_register_handlers(self, message_handler, mock_dispatcher):
        """Тест регистрации обработчиков в диспетчере"""
        message_handler.register_handlers(mock_dispatcher)
        
        mock_dispatcher.message.register.assert_called_once_with(message_handler.handle_message)
        mock_dispatcher.callback_query.register.assert_called_once_with(message_handler.handle_callback)
        message_handler.logger.info.assert_called_once_with("Message handlers registered successfully")

    # Тесты валидации
    @pytest.mark.asyncio
    async def test_validate_input_success(self, message_handler, mock_message):
        """Тест успешной валидации входных данных"""
        result = await message_handler._validate_input(mock_message)
        
        assert result is True
        message_handler.validate_user.assert_called_once_with(12345)
        message_handler.check_rate_limit.assert_called_once_with(12345, "message", 30, 60)

    @pytest.mark.asyncio
    async def test_validate_input_no_user(self, message_handler, mock_message):
        """Тест валидации без информации о пользователе"""
        mock_message.from_user = None
        
        result = await message_handler._validate_input(mock_message)
        
        assert result is False
        message_handler.logger.warning.assert_called_once_with("Message or callback has no user information")

    @pytest.mark.asyncio
    async def test_validate_input_rate_limit_exceeded(self, message_handler, mock_message):
        """Тест валидации с превышением rate limit"""
        message_handler.check_rate_limit = AsyncMock(return_value=False)
        message_handler._show_rate_limit_message = AsyncMock()
        
        result = await message_handler._validate_input(mock_message)
        
        assert result is False
        message_handler._show_rate_limit_message.assert_called_once_with(mock_message, "message")

    @pytest.mark.asyncio
    async def test_validate_input_user_validation_failed(self, message_handler, mock_message):
        """Тест валидации с проваленной проверкой пользователя"""
        message_handler.validate_user = AsyncMock(return_value=False)
        
        result = await message_handler._validate_input(mock_message)
        
        assert result is False
        message_handler.logger.error.assert_called_once_with("User validation failed for 12345")

    # Тесты логирования событий
    @pytest.mark.asyncio
    async def test_log_event_success(self, message_handler):
        """Тест успешного логирования события"""
        await message_handler._log_event("test_event", 12345, "test_data")
        
        message_handler.logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_event_critical(self, message_handler):
        """Тест логирования критического события"""
        await message_handler._log_event("callback", 12345, "payment_100")
        
        # Должно быть 2 вызова: общий и критический
        assert message_handler.logger.info.call_count == 2

    @pytest.mark.asyncio
    async def test_log_event_exception(self, message_handler):
        """Тест логирования с исключением"""
        message_handler.logger.info.side_effect = Exception("Log error")
        
        # Должно обработать исключение без падения
        await message_handler._log_event("test_event", 12345, "test_data")
        
        message_handler.logger.error.assert_called_once_with("Error logging event: Log error")

    # Тесты приватных методов обработки команд
    @pytest.mark.asyncio
    async def test_handle_start_command_message(self, message_handler, mock_message, mock_bot):
        """Тест обработки команды start для сообщения"""
        await message_handler._handle_start_command(mock_message, mock_bot)
        
        mock_message.answer.assert_called_once()
        args, kwargs = mock_message.answer.call_args
        assert "Добро пожаловать" in kwargs.get('text', '') or "Добро пожаловать" in (args[0] if args else '')
        assert kwargs.get('parse_mode') == "HTML"

    @pytest.mark.asyncio
    async def test_handle_help_command_message(self, message_handler, mock_message, mock_bot):
        """Тест обработки команды help для сообщения"""
        await message_handler._handle_help_command(mock_message, mock_bot)
        
        mock_message.answer.assert_called_once()
        args, kwargs = mock_message.answer.call_args
        assert "Помощь" in kwargs.get('text', '') or "Помощь" in (args[0] if args else '')
        assert kwargs.get('parse_mode') == "HTML"

    @pytest.mark.asyncio
    async def test_handle_unknown_command(self, message_handler, mock_message):
        """Тест обработки неизвестной команды"""
        await message_handler._handle_unknown_command(mock_message)
        
        mock_message.answer.assert_called_once_with(
            MessageTemplate.get_unknown_command(), parse_mode="HTML"
        )

    @pytest.mark.asyncio
    async def test_handle_unknown_callback(self, message_handler, mock_callback):
        """Тест обработки неизвестного callback"""
        await message_handler._handle_unknown_callback(mock_callback)
        
        mock_callback.answer.assert_called_once_with(
            MessageTemplate.get_unknown_callback(), show_alert=True
        )

    # Тесты rate limit сообщений
    @pytest.mark.asyncio
    async def test_show_rate_limit_message_message(self, message_handler, mock_message):
        """Тест показа сообщения о rate limit для сообщения"""
        await message_handler._show_rate_limit_message(mock_message, "message")
        
        mock_message.answer.assert_called_once()
        args, kwargs = mock_message.answer.call_args
        assert kwargs.get('parse_mode') == "HTML"

    @pytest.mark.asyncio
    async def test_show_rate_limit_message_callback(self, message_handler, mock_callback):
        """Тест показа сообщения о rate limit для callback"""
        await message_handler._show_rate_limit_message(mock_callback, "message")
        
        mock_callback.answer.assert_called_once()
        args, kwargs = mock_callback.answer.call_args
        assert kwargs.get('show_alert') is True

    @pytest.mark.asyncio
    async def test_show_rate_limit_message_no_user(self, message_handler, mock_message):
        """Тест показа сообщения о rate limit без пользователя"""
        mock_message.from_user = None
        
        await message_handler._show_rate_limit_message(mock_message, "message")
        
        message_handler.logger.error.assert_called_once_with(
            "Cannot show rate limit message: no user information"
        )
        mock_message.answer.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])