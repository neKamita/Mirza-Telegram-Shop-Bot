"""
Утилиты для retry с экспоненциальной задержкой и обработкой ошибок
"""
import asyncio
import logging
import time
from typing import Callable, Any, Optional, Dict, Type, Tuple
from functools import wraps
import aiohttp
from dataclasses import dataclass


@dataclass
class RetryConfig:
    """Конфигурация для retry механизма"""
    max_retries: int = 3
    initial_delay: float = 1.0  # секунды
    max_delay: float = 30.0  # секунды
    backoff_factor: float = 2.0
    jitter: float = 0.1
    retry_on_status_codes: Tuple[int, ...] = (429, 500, 502, 503, 504)
    retry_on_exceptions: Tuple[Type[Exception], ...] = (
        aiohttp.ClientError,
        asyncio.TimeoutError,
        ConnectionError,
        TimeoutError
    )


class RetryError(Exception):
    """Исключение при исчерпании попыток retry"""
    def __init__(self, message: str, last_exception: Optional[Exception] = None):
        super().__init__(message)
        self.last_exception = last_exception


def async_retry(config: Optional[RetryConfig] = None):
    """
    Декоратор для асинхронных функций с retry логикой
    
    Args:
        config: Конфигурация retry (опционально)
    
    Returns:
        Декорированную функцию с retry
    """
    config = config or RetryConfig()
    
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            retry_count = 0
            
            while retry_count <= config.max_retries:
                try:
                    if retry_count > 0:
                        # Вычисляем задержку с экспоненциальным откатом и jitter
                        delay = min(
                            config.initial_delay * (config.backoff_factor ** (retry_count - 1)),
                            config.max_delay
                        )
                        # Добавляем jitter для распределения нагрузки
                        jitter_amount = delay * config.jitter
                        actual_delay = delay + (jitter_amount * (2 * (time.time() % 1) - 1))
                        
                        logging.getLogger(__name__).info(
                            f"Retry {retry_count}/{config.max_retries} for {func.__name__}, "
                            f"waiting {actual_delay:.2f}s before next attempt"
                        )
                        
                        await asyncio.sleep(actual_delay)
                    
                    result = await func(*args, **kwargs)
                    
                    # Проверяем HTTP статус код для retry
                    if isinstance(result, dict) and 'status_code' in result:
                        status_code = result['status_code']
                        if status_code in config.retry_on_status_codes and retry_count < config.max_retries:
                            logging.getLogger(__name__).warning(
                                f"HTTP {status_code} received, retrying {func.__name__} "
                                f"(attempt {retry_count + 1}/{config.max_retries})"
                            )
                            retry_count += 1
                            continue
                    
                    return result
                    
                except config.retry_on_exceptions as e:
                    last_exception = e
                    retry_count += 1
                    
                    if retry_count > config.max_retries:
                        break
                        
                    logging.getLogger(__name__).warning(
                        f"Exception in {func.__name__}: {e}, "
                        f"retrying (attempt {retry_count}/{config.max_retries})"
                    )
                    
                except Exception as e:
                    # Неожиданные исключения не retry
                    logging.getLogger(__name__).error(
                        f"Unexpected exception in {func.__name__}: {e}"
                    )
                    raise
            
            # Если дошли сюда, значит исчерпали все попытки
            error_msg = (
                f"Function {func.__name__} failed after {config.max_retries} retries"
            )
            logging.getLogger(__name__).error(error_msg)
            raise RetryError(error_msg, last_exception)
        
        return wrapper
    
    return decorator


def sync_retry(config: Optional[RetryConfig] = None):
    """
    Декоратор для синхронных функций с retry логикой
    
    Args:
        config: Конфигурация retry (опционально)
    
    Returns:
        Декорированную функцию с retry
    """
    config = config or RetryConfig()
    
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            retry_count = 0
            
            while retry_count <= config.max_retries:
                try:
                    if retry_count > 0:
                        # Вычисляем задержку с экспоненциальным откатом и jitter
                        delay = min(
                            config.initial_delay * (config.backoff_factor ** (retry_count - 1)),
                            config.max_delay
                        )
                        # Добавляем jitter для распределения нагрузки
                        jitter_amount = delay * config.jitter
                        actual_delay = delay + (jitter_amount * (2 * (time.time() % 1) - 1))
                        
                        logging.getLogger(__name__).info(
                            f"Retry {retry_count}/{config.max_retries} for {func.__name__}, "
                            f"waiting {actual_delay:.2f}s before next attempt"
                        )
                        
                        time.sleep(actual_delay)
                    
                    result = func(*args, **kwargs)
                    
                    # Проверяем HTTP статус код для retry
                    if isinstance(result, dict) and 'status_code' in result:
                        status_code = result['status_code']
                        if status_code in config.retry_on_status_codes and retry_count < config.max_retries:
                            logging.getLogger(__name__).warning(
                                f"HTTP {status_code} received, retrying {func.__name__} "
                                f"(attempt {retry_count + 1}/{config.max_retries})"
                            )
                            retry_count += 1
                            continue
                    
                    return result
                    
                except config.retry_on_exceptions as e:
                    last_exception = e
                    retry_count += 1
                    
                    if retry_count > config.max_retries:
                        break
                        
                    logging.getLogger(__name__).warning(
                        f"Exception in {func.__name__}: {e}, "
                        f"retrying (attempt {retry_count}/{config.max_retries})"
                    )
                    
                except Exception as e:
                    # Неожиданные исключения не retry
                    logging.getLogger(__name__).error(
                        f"Unexpected exception in {func.__name__}: {e}"
                    )
                    raise
            
            # Если дошли сюда, значит исчерпали все попытки
            error_msg = (
                f"Function {func.__name__} failed after {config.max_retries} retries"
            )
            logging.getLogger(__name__).error(error_msg)
            raise RetryError(error_msg, last_exception)
        
        return wrapper
    
    return decorator


# Готовые конфигурации для различных сервисов
class RetryConfigs:
    """Предустановленные конфигурации retry для различных сервисов"""
    
    @staticmethod
    def telegram_api() -> RetryConfig:
        """Конфигурация для Telegram API"""
        return RetryConfig(
            max_retries=3,
            initial_delay=1.0,
            max_delay=10.0,
            backoff_factor=2.0,
            retry_on_status_codes=(429, 500, 502, 503, 504),
            retry_on_exceptions=(
                aiohttp.ClientError,
                asyncio.TimeoutError,
                ConnectionError,
            )
        )
    
    @staticmethod
    def payment_service() -> RetryConfig:
        """Конфигурация для платежной системы"""
        return RetryConfig(
            max_retries=5,
            initial_delay=1.0,
            max_delay=30.0,
            backoff_factor=2.0,
            retry_on_status_codes=(429, 500, 502, 503, 504, 404),
            retry_on_exceptions=(
                aiohttp.ClientError,
                asyncio.TimeoutError,
                ConnectionError,
            )
        )
    
    @staticmethod
    def database() -> RetryConfig:
        """Конфигурация для базы данных"""
        return RetryConfig(
            max_retries=3,
            initial_delay=0.5,
            max_delay=5.0,
            backoff_factor=1.5,
            retry_on_status_codes=(),
            retry_on_exceptions=(
                ConnectionError,
                TimeoutError,
            )
        )

    @staticmethod
    def fragment_service() -> RetryConfig:
        """Конфигурация для Fragment API"""
        return RetryConfig(
            max_retries=5,
            initial_delay=1.0,
            max_delay=30.0,
            backoff_factor=2.0,
            jitter=0.2,
            retry_on_status_codes=(429, 500, 502, 503, 504),
            retry_on_exceptions=(
                aiohttp.ClientError,
                asyncio.TimeoutError,
                ConnectionError,
            )
        )