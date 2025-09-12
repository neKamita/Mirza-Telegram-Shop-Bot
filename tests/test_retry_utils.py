"""
Тесты для утилит retry с экспоненциальной задержкой
"""
import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock, Mock
from datetime import datetime

from utils.retry_utils import (
    async_retry, 
    sync_retry, 
    RetryConfig, 
    RetryError,
    RetryConfigs
)
import aiohttp


class TestRetryUtils:
    """Тесты для утилит retry"""

    @pytest.mark.asyncio
    async def test_async_retry_success_first_attempt(self):
        """Тест успешного выполнения с первой попытки"""
        mock_func = AsyncMock(return_value={"success": True})
        
        decorated_func = async_retry()(mock_func)
        result = await decorated_func()
        
        assert result == {"success": True}
        mock_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_retry_success_after_retries(self):
        """Тест успешного выполнения после нескольких попыток"""
        mock_func = AsyncMock()
        mock_func.side_effect = [
            aiohttp.ClientError("Connection failed"),
            aiohttp.ClientError("Connection failed"), 
            {"success": True}
        ]
        
        decorated_func = async_retry(RetryConfig(max_retries=3))(mock_func)
        result = await decorated_func()
        
        assert result == {"success": True}
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_async_retry_max_retries_exceeded(self):
        """Тест исчерпания максимального количества попыток"""
        mock_func = AsyncMock(side_effect=aiohttp.ClientError("Connection failed"))
        
        decorated_func = async_retry(RetryConfig(max_retries=2))(mock_func)
        
        with pytest.raises(RetryError) as exc_info:
            await decorated_func()
        
        assert "failed after 2 retries" in str(exc_info.value)
        assert mock_func.call_count == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_async_retry_with_http_status_codes(self):
        """Тест retry для HTTP статус кодов"""
        mock_func = AsyncMock()
        mock_func.side_effect = [
            {"status_code": 429, "error": "Rate limited"},
            {"status_code": 500, "error": "Server error"},
            {"status_code": 200, "success": True}
        ]
        
        decorated_func = async_retry(RetryConfig(max_retries=3))(mock_func)
        result = await decorated_func()
        
        assert result == {"status_code": 200, "success": True}
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_async_retry_exponential_backoff_timing(self):
        """Тест timing экспоненциального backoff"""
        mock_func = AsyncMock(side_effect=aiohttp.ClientError("Connection failed"))
        config = RetryConfig(
            max_retries=3,
            initial_delay=0.1,
            backoff_factor=2.0,
            jitter=0.0  # Отключаем jitter для точного тестирования
        )
        
        decorated_func = async_retry(config)(mock_func)
        start_time = time.time()
        
        with pytest.raises(RetryError):
            await decorated_func()
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        # Ожидаемое время: 0s (первая попытка) + 0.1s + 0.2s + 0.4s = ~0.7s
        assert 0.6 <= elapsed_time <= 0.8
        assert mock_func.call_count == 4  # 1 initial + 3 retries

    @pytest.mark.asyncio
    async def test_async_retry_jitter_variation(self):
        """Тест вариации jitter в задержках"""
        mock_func = AsyncMock(side_effect=aiohttp.ClientError("Connection failed"))
        config = RetryConfig(
            max_retries=2,
            initial_delay=0.1,
            backoff_factor=2.0,
            jitter=0.5  # Большой jitter для тестирования вариации
        )
        
        decorated_func = async_retry(config)(mock_func)
        
        # Запускаем несколько раз чтобы проверить вариацию jitter
        times = []
        for _ in range(3):
            start_time = time.time()
            with pytest.raises(RetryError):
                await decorated_func()
            end_time = time.time()
            times.append(end_time - start_time)
            mock_func.reset_mock()
        
        # Времена должны немного отличаться из-за jitter
        assert len(set(round(t, 2) for t in times)) > 1

    @pytest.mark.asyncio
    async def test_async_retry_unexpected_exception(self):
        """Тест неожиданных исключений (не должны retry)"""
        mock_func = AsyncMock(side_effect=ValueError("Unexpected error"))
        
        decorated_func = async_retry()(mock_func)
        
        with pytest.raises(ValueError, match="Unexpected error"):
            await decorated_func()
        
        mock_func.assert_called_once()  # Только одна попытка

    @pytest.mark.asyncio
    async def test_async_retry_max_delay_respected(self):
        """Тест ограничения максимальной задержки"""
        mock_func = AsyncMock(side_effect=aiohttp.ClientError("Connection failed"))
        config = RetryConfig(
            max_retries=5,
            initial_delay=10.0,  # Большая начальная задержка
            max_delay=1.0,       # Но максимальная ограничена
            backoff_factor=2.0
        )
        
        decorated_func = async_retry(config)(mock_func)
        start_time = time.time()
        
        with pytest.raises(RetryError):
            await decorated_func()
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        # Все задержки должны быть ограничены max_delay=1.0
        # 5 retries * 1.0s = ~5s + немного времени на выполнение
        assert 4.5 <= elapsed_time <= 6.0

    def test_sync_retry_functionality(self):
        """Тест синхронного retry декоратора"""
        mock_func = Mock()
        mock_func.__name__ = "mock_func"  # Добавляем __name__ для логирования
        mock_func.side_effect = [
            ConnectionError("Connection failed"),
            ConnectionError("Connection failed"),
            "success"
        ]
        
        decorated_func = sync_retry(RetryConfig(max_retries=2))(mock_func)
        result = decorated_func()
        
        assert result == "success"
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_configs_presets(self):
        """Тест предустановленных конфигураций"""
        # Telegram API config
        telegram_config = RetryConfigs.telegram_api()
        assert telegram_config.max_retries == 3
        assert 429 in telegram_config.retry_on_status_codes
        
        # Payment service config
        payment_config = RetryConfigs.payment_service()
        assert payment_config.max_retries == 5
        assert 404 in payment_config.retry_on_status_codes
        
        # Fragment service config
        fragment_config = RetryConfigs.fragment_service()
        assert fragment_config.max_retries == 5
        assert fragment_config.jitter == 0.2

    @pytest.mark.asyncio
    async def test_retry_with_custom_exceptions(self):
        """Тест retry с пользовательскими исключениями"""
        class CustomException(Exception):
            pass
        
        mock_func = AsyncMock(side_effect=CustomException("Custom error"))
        config = RetryConfig(
            max_retries=2,
            retry_on_exceptions=(CustomException,)
        )
        
        decorated_func = async_retry(config)(mock_func)
        
        with pytest.raises(RetryError):
            await decorated_func()
        
        assert mock_func.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_skips_non_retryable_status_codes(self):
        """Тест пропуска retry для не-retryable статус кодов"""
        mock_func = AsyncMock(return_value={"status_code": 400, "error": "Bad Request"})
        
        decorated_func = async_retry()(mock_func)
        result = await decorated_func()
        
        assert result == {"status_code": 400, "error": "Bad Request"}
        mock_func.assert_called_once()  # 400 не входит в retry_on_status_codes


if __name__ == "__main__":
    pytest.main([__file__])