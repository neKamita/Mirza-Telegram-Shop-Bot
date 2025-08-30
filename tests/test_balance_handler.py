"""
Тесты для BalanceHandler
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from aiogram.types import Message, CallbackQuery, User, Chat
from aiogram import Bot

from handlers.balance_handler import BalanceHandler
from services.balance.balance_service import BalanceService
from handlers.error_handler import ErrorHandler


class TestBalanceHandler:
    """Тесты для BalanceHandler"""

    @pytest.fixture
    def balance_handler(self):
        """Фикстура для создания экземпляра BalanceHandler"""
        # Создаем моки для всех зависимостей BaseHandler
        user_repository = Mock()
        payment_service = Mock()
        balance_service = Mock(spec=BalanceService)
        star_purchase_service = Mock()
        session_cache = Mock()
        rate_limit_cache = Mock()
        payment_cache = Mock()
        
        # Создаем обработчик с моками
        handler = BalanceHandler(
            user_repository=user_repository,
            payment_service=payment_service,
            balance_service=balance_service,
            star_purchase_service=star_purchase_service,
            session_cache=session_cache,
            rate_limit_cache=rate_limit_cache,
            payment_cache=payment_cache
        )
        
        # Дополнительные моки
        handler.error_handler = Mock(spec=ErrorHandler)
        handler.logger = Mock()
        handler.check_rate_limit = AsyncMock(return_value=True)
        handler.get_rate_limit_remaining_time = AsyncMock(return_value=30)
        
        return handler

    @pytest.fixture
    def mock_message(self):
        """Фикстура для создания мока сообщения"""
        message = Mock(spec=Message)
        message.from_user = Mock(spec=User)
        message.from_user.id = 123
        message.text = "/balance"
        message.answer = AsyncMock()
        message.edit_text = AsyncMock()
        return message

    @pytest.fixture
    def mock_callback(self):
        """Фикстура для создания мока callback"""
        callback = Mock(spec=CallbackQuery)
        callback.from_user = Mock(spec=User)
        callback.from_user.id = 123
        callback.data = "balance"
        callback.answer = AsyncMock()
        callback.message = Mock(spec=Message)
        callback.message.edit_text = AsyncMock()
        return callback

    @pytest.fixture
    def mock_bot(self):
        """Фикстура для создания мока бота"""
        return Mock(spec=Bot)

    @pytest.mark.asyncio
    async def test_show_balance_success(self, balance_handler, mock_message, mock_bot):
        """Тест успешного отображения баланса"""
        # Настраиваем моки
        balance_data = {
            "balance": 100.0,
            "currency": "TON", 
            "source": "cache"
        }
        balance_handler.balance_service.get_user_balance = AsyncMock(return_value=balance_data)
        
        # Вызываем метод
        await balance_handler.show_balance(mock_message, mock_bot)
        
        # Проверяем вызовы
        balance_handler.balance_service.get_user_balance.assert_called_once_with(123)
        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_balance_no_user_info(self, balance_handler, mock_message, mock_bot):
        """Тест отображения баланса без информации о пользователе"""
        # Убираем информацию о пользователе
        mock_message.from_user = None
        
        # Вызываем метод
        await balance_handler.show_balance(mock_message, mock_bot)
        
        # Проверяем логирование
        balance_handler.logger.warning.assert_called_once_with("User information is missing in show_balance")
        mock_message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_show_balance_service_error(self, balance_handler, mock_message, mock_bot):
        """Тест отображения баланса с ошибкой сервиса"""
        # Настраиваем моки для ошибки
        balance_handler.balance_service.get_user_balance = AsyncMock(return_value=None)
        
        # Вызываем метод
        await balance_handler.show_balance(mock_message, mock_bot)
        
        # Проверяем вызовы
        balance_handler.balance_service.get_user_balance.assert_called_once_with(123)
        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_balance_callback_success(self, balance_handler, mock_callback, mock_bot):
        """Тест успешного отображения баланса через callback"""
        # Настраиваем моки
        balance_data = {
            "balance": 150.0,
            "currency": "TON",
            "source": "database"
        }
        balance_handler.balance_service.get_user_balance = AsyncMock(return_value=balance_data)
        
        # Вызываем метод
        await balance_handler.show_balance(mock_callback, mock_bot)
        
        # Проверяем вызовы
        balance_handler.balance_service.get_user_balance.assert_called_once_with(123)
        mock_callback.message.edit_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_balance_history_success(self, balance_handler, mock_callback, mock_bot):
        """Тест успешного отображения истории баланса"""
        # Настраиваем моки
        history_data = {
            "initial_balance": 50.0,
            "final_balance": 150.0,
            "transactions_count": 3,
            "transactions": [
                {
                    "transaction_type": "recharge",
                    "amount": 100.0,
                    "status": "completed",
                    "created_at": "2024-01-01T10:00:00Z"
                }
            ]
        }
        balance_handler.balance_service.get_user_balance_history = AsyncMock(return_value=history_data)
        balance_handler.check_rate_limit = AsyncMock(return_value=True)
        
        # Вызываем метод
        await balance_handler.show_balance_history(mock_callback, mock_bot)
        
        # Проверяем вызовы
        balance_handler.balance_service.get_user_balance_history.assert_called_once_with(123, days=30)
        mock_callback.message.edit_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_balance_history_no_transactions(self, balance_handler, mock_callback, mock_bot):
        """Тест отображения истории баланса без транзакций"""
        # Настраиваем моки
        history_data = {
            "transactions_count": 0
        }
        balance_handler.balance_service.get_user_balance_history = AsyncMock(return_value=history_data)
        balance_handler.check_rate_limit = AsyncMock(return_value=True)
        
        # Вызываем метод
        await balance_handler.show_balance_history(mock_callback, mock_bot)
        
        # Проверяем вызовы
        balance_handler.balance_service.get_user_balance_history.assert_called_once_with(123, days=30)
        mock_callback.message.edit_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_balance_history_rate_limit(self, balance_handler, mock_callback, mock_bot):
        """Тест ограничения rate limit для истории баланса"""
        # Настраиваем моки
        balance_handler.check_rate_limit = AsyncMock(return_value=False)
        balance_handler._show_rate_limit_message = AsyncMock()
        
        # Вызываем метод
        await balance_handler.show_balance_history(mock_callback, mock_bot)
        
        # Проверяем вызовы
        balance_handler.check_rate_limit.assert_called_once_with(123, "operation", 20, 60)
        balance_handler._show_rate_limit_message.assert_called_once_with(mock_callback, "operation")
        balance_handler.balance_service.get_user_balance_history.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_balance_command(self, balance_handler, mock_message, mock_bot):
        """Тест обработки сообщения с командой баланса"""
        # Настраиваем моки
        mock_message.text = "мой баланс"
        balance_handler.show_balance = AsyncMock()
        
        # Вызываем метод
        await balance_handler.handle_message(mock_message, mock_bot)
        
        # Проверяем вызовы
        balance_handler.show_balance.assert_called_once_with(mock_message, mock_bot)

    @pytest.mark.asyncio
    async def test_handle_message_unknown_command(self, balance_handler, mock_message, mock_bot):
        """Тест обработки неизвестной команды"""
        # Настраиваем моки
        mock_message.text = "неизвестная команда"
        
        # Вызываем метод
        await balance_handler.handle_message(mock_message, mock_bot)
        
        # Проверяем вызовы
        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_callback_balance(self, balance_handler, mock_callback, mock_bot):
        """Тест обработки callback для баланса"""
        # Настраиваем моки
        mock_callback.data = "balance"
        balance_handler.show_balance = AsyncMock()
        
        # Вызываем метод
        await balance_handler.handle_callback(mock_callback, mock_bot)
        
        # Проверяем вызовы
        balance_handler.show_balance.assert_called_once_with(mock_callback, mock_bot)

    @pytest.mark.asyncio
    async def test_handle_callback_balance_history(self, balance_handler, mock_callback, mock_bot):
        """Тест обработки callback для истории баланса"""
        # Настраиваем моки
        mock_callback.data = "balance_history"
        balance_handler.show_balance_history = AsyncMock()
        
        # Вызываем метод
        await balance_handler.handle_callback(mock_callback, mock_bot)
        
        # Проверяем вызовы
        balance_handler.show_balance_history.assert_called_once_with(mock_callback, mock_bot)

    @pytest.mark.asyncio
    async def test_handle_callback_unknown(self, balance_handler, mock_callback, mock_bot):
        """Тест обработки неизвестного callback"""
        # Настраиваем моки
        mock_callback.data = "unknown_action"
        
        # Вызываем метод
        await balance_handler.handle_callback(mock_callback, mock_bot)
        
        # Проверяем вызовы
        mock_callback.answer.assert_called_once_with(
            "❓ <b>Неизвестное действие</b> ❓\n\n"
            "🔍 <i>Пожалуйста, используйте доступные кнопки</i>\n\n"
            "💡 <i>Введите /start для возврата в меню</i>",
            show_alert=True
        )

    @pytest.mark.asyncio
    async def test_show_rate_limit_message_message(self, balance_handler, mock_message):
        """Тест показа сообщения о rate limit для сообщения"""
        # Вызываем метод
        await balance_handler._show_rate_limit_message(mock_message, "operation")
        
        # Проверяем вызовы
        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_rate_limit_message_callback(self, balance_handler, mock_callback):
        """Тест показа сообщения о rate limit для callback"""
        # Вызываем метод
        await balance_handler._show_rate_limit_message(mock_callback, "operation")
        
        # Проверяем вызовы
        mock_callback.answer.assert_called_once_with(
            "🔄 ⏳ Подождите немного\n\n"
            "📝 Слишком много операций за короткое время\n\n"
            "⏰ Попробуйте через 30 сек.\n\n"
            "💡 Это защищает сервис от перегрузки",
            show_alert=True
        )

    @pytest.mark.asyncio
    async def test_show_rate_limit_message_no_user(self, balance_handler, mock_message):
        """Тест показа сообщения о rate limit без информации о пользователе"""
        # Убираем информацию о пользователе
        mock_message.from_user = None
        
        # Вызываем метод
        await balance_handler._show_rate_limit_message(mock_message, "operation")
        
        # Проверяем логирование
        balance_handler.logger.warning.assert_called_once_with(
            "User information is missing in _show_rate_limit_message"
        )
        mock_message.answer.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])