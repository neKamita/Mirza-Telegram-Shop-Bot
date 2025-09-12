"""
Сервис для интеграции с Telegram Fragment API для покупки звезд
"""
import logging
import os
from typing import Dict, Any, Optional, Callable

from fragment_api_lib.client import FragmentAPIClient
from fragment_api_lib.models import *

from config.settings import settings
from services.system.circuit_breaker import circuit_manager, CircuitConfigs
from utils.retry_utils import async_retry, RetryConfigs, RetryError


class FragmentService:
    """Сервис для работы с Telegram Fragment API"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.client = FragmentAPIClient()
        
        # Получаем настройки из переменных окружения
        self.seed_phrase = os.getenv("FRAGMENT_SEED_PHRASE", "")
        self.fragment_cookies = os.getenv("FRAGMENT_COOKIES", "")
        
        # Инициализируем менеджер cookies позже, когда он будет нужен
        self._cookie_manager = None
        
        # Инициализация circuit breaker для Fragment API
        self.circuit_breaker = circuit_manager.create_circuit(
            "fragment_service",
            CircuitConfigs.fragment_service()
        )
        
        # Проверяем формат seed phrase
        self._validate_seed_phrase()
            
        if not self.fragment_cookies:
            self.logger.warning("FRAGMENT_COOKIES is not set in environment variables")
    
    @property
    def cookie_manager(self):
        """Ленивая инициализация FragmentCookieManager для избежания циклической зависимости"""
        if self._cookie_manager is None:
            from services.fragment.fragment_cookie_manager import FragmentCookieManager
            self._cookie_manager = FragmentCookieManager(self)
        return self._cookie_manager
    
    def _validate_seed_phrase(self) -> bool:
        """Проверка формата seed phrase"""
        if not self.seed_phrase:
            self.logger.error("FRAGMENT_SEED_PHRASE is not set in environment variables")
            return False
            
        # Проверяем значение по умолчанию
        if self.seed_phrase in ["your_24_words_seed_phrase", "your_24_words_seed_phrase_from_ton_v4r2_wallet"]:
            self.logger.error("FRAGMENT_SEED_PHRASE contains default placeholder value. Please set real seed phrase.")
            return False
        
        # Проверяем количество слов
        words = self.seed_phrase.strip().split()
        if len(words) != 24:
            self.logger.error(f"Invalid seed phrase format: expected 24 words, got {len(words)}")
            return False
        
        self.logger.info("Seed phrase format is valid (24 words)")
        return True

    async def refresh_cookies_if_needed(self) -> bool:
        """
        Обновление cookies при необходимости
        Возвращает True если cookies были обновлены или уже действительны
        """
        try:
            # Проверяем, включено ли автоматическое обновление
            auto_refresh = os.getenv("FRAGMENT_AUTO_COOKIE_REFRESH", "False").lower() == "true"
            if not auto_refresh:
                return True
                
            # Проверяем валидность текущих cookies
            if self.fragment_cookies:
                expired = await self.cookie_manager._are_cookies_expired(self.fragment_cookies)
                if not expired:
                    return True  # Cookies действительны
            
            # Обновляем cookies
            self.logger.info("Fragment cookies expired or missing, refreshing...")
            new_cookies = await self.cookie_manager._refresh_cookies()
            
            if new_cookies:
                # Сохраняем новые cookies
                await self.cookie_manager._save_cookies_to_file(new_cookies)
                
                # Обновляем переменные
                self.fragment_cookies = new_cookies
                os.environ["FRAGMENT_COOKIES"] = new_cookies
                
                self.logger.info("Fragment cookies refreshed successfully")
                return True
            else:
                self.logger.error("Failed to refresh Fragment cookies")
                return False
                
        except Exception as e:
            self.logger.error(f"Error refreshing Fragment cookies: {e}")
            return False

    @async_retry(RetryConfigs.fragment_service())
    async def _make_api_call(self, api_method, *args, **kwargs) -> Dict[str, Any]:
        """
        Обертка для API вызовов с автоматическим обновлением cookies
        Использует circuit breaker и retry механизм
        """
        async def _execute_with_circuit_breaker():
            # Сначала пытаемся выполнить вызов с текущими cookies
            try:
                result = api_method(*args, **kwargs)
                return {
                    "status": "success",
                    "result": result
                }
            except Exception as e:
                # Если ошибка связана с cookies, пытаемся обновить их
                error_str = str(e).lower()
                if "cookie" in error_str or "auth" in error_str or "unauthorized" in error_str:
                    self.logger.warning(f"API call failed with auth error: {e}, trying to refresh cookies")
                    
                    # Обновляем cookies
                    if await self.refresh_cookies_if_needed():
                        # Повторяем вызов с новыми cookies
                        try:
                            result = api_method(*args, **kwargs)
                            return {
                                "status": "success",
                                "result": result
                            }
                        except Exception as retry_error:
                            self.logger.error(f"API call failed after cookie refresh: {retry_error}")
                            return {
                                "status": "failed",
                                "error": str(retry_error)
                            }
                    else:
                        return {
                            "status": "failed",
                            "error": "Failed to refresh cookies"
                        }
                else:
                    # Другая ошибка, не связанная с cookies
                    self.logger.error(f"API call failed: {e}")
                    return {
                        "status": "failed",
                        "error": str(e)
                    }

        # Используем circuit breaker для выполнения вызова
        try:
            result = await self.circuit_breaker.call(_execute_with_circuit_breaker)
            return result
        except Exception as e:
            self.logger.error(f"Circuit breaker failed for API call: {e}")
            return {
                "status": "failed",
                "error": f"Circuit breaker error: {str(e)}"
            }


    async def ping(self) -> Dict[str, Any]:
        """Пинг API"""
        # Используем новый механизм с circuit breaker и retry
        return await self._make_api_call(
            lambda: self.client.ping()
        )

    async def get_balance(self) -> Dict[str, Any]:
        """Получение баланса кошелька"""
        if not self.seed_phrase:
            return {
                "status": "failed",
                "error": "Seed phrase is not configured"
            }
            
        # Используем новый механизм с circuit breaker и retry
        return await self._make_api_call(
            lambda: self.client.get_balance(seed=self.seed_phrase)
        )

    async def get_user_info(self, username: str) -> Dict[str, Any]:
        """Получение информации о пользователе"""
        if not self.fragment_cookies:
            return {
                "status": "failed",
                "error": "Fragment cookies are not configured"
            }
            
        # Используем новый механизм с circuit breaker и retry
        return await self._make_api_call(
            lambda: self.client.get_user_info(
                username=username,
                fragment_cookies=self.fragment_cookies
            )
        )

    async def buy_stars_without_kyc(self, username: str, amount: int) -> Dict[str, Any]:
        """Покупка звезд без KYC"""
        if not self.seed_phrase:
            return {
                "status": "failed",
                "error": "Seed phrase is not configured"
            }
            
        # Используем новый механизм с circuit breaker и retry
        return await self._make_api_call(
            lambda: self.client.buy_stars_without_kyc(
                username=username,
                amount=amount,
                seed=self.seed_phrase
            )
        )

    async def buy_stars(self, username: str, amount: int, show_sender: bool = False) -> Dict[str, Any]:
        """Покупка звезд (с KYC)"""
        if not self.seed_phrase:
            return {
                "status": "failed",
                "error": "Seed phrase is not configured"
            }
            
        if not self.fragment_cookies:
            return {
                "status": "failed",
                "error": "Fragment cookies are not configured"
            }
            
        # Используем новый механизм с circuit breaker и retry
        return await self._make_api_call(
            lambda: self.client.buy_stars(
                username=username,
                amount=amount,
                show_sender=show_sender,
                fragment_cookies=self.fragment_cookies,
                seed=self.seed_phrase
            )
        )

    async def buy_premium_without_kyc(self, username: str, duration: int) -> Dict[str, Any]:
        """Покупка Telegram Premium без KYC"""
        if not self.seed_phrase:
            return {
                "status": "failed",
                "error": "Seed phrase is not configured"
            }
            
        # Используем новый механизм с circuit breaker и retry
        return await self._make_api_call(
            lambda: self.client.buy_premium_without_kyc(
                username=username,
                duration=duration,
                seed=self.seed_phrase
            )
        )

    async def buy_premium(self, username: str, duration: int, show_sender: bool = False) -> Dict[str, Any]:
        """Покупка Telegram Premium (с KYC)"""
        if not self.seed_phrase:
            return {
                "status": "failed",
                "error": "Seed phrase is not configured"
            }
            
        if not self.fragment_cookies:
            return {
                "status": "failed",
                "error": "Fragment cookies are not configured"
            }
            
        # Используем новый механизм с circuit breaker и retry
        return await self._make_api_call(
            lambda: self.client.buy_premium(
                username=username,
                duration=duration,
                show_sender=show_sender,
                fragment_cookies=self.fragment_cookies,
                seed=self.seed_phrase
            )
        )