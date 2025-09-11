"""
Сервис для автоматического получения и обновления Fragment cookies
"""
import asyncio
import logging
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

# Импортируем Fragme, timezonentService для типизации
from services.fragment.fragment_service import FragmentService

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from chromedriver_py import binary_path
    SELENIUM_AVAILABLE = True
    CHROMEDRIVER_PY_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    CHROMEDRIVER_PY_AVAILABLE = False
    logging.warning("Selenium not available, automatic cookie refresh will be disabled")


class FragmentCookieManager:
    """Менеджер для автоматического получения и обновления Fragment cookies"""
    
    def __init__(self, fragment_service):
        self.fragment_service = fragment_service
        self.logger = logging.getLogger(__name__)
        self.cookies_file = Path("fragment_cookies.json")
        self.cookie_refresh_interval = int(os.getenv("FRAGMENT_COOKIE_REFRESH_INTERVAL", "3600"))  # 1 час по умолчанию
        
    async def get_fragment_cookies(self) -> Optional[str]:
        """
        Получение Fragment cookies с автоматическим обновлением при необходимости
        """
        try:
            # Проверяем, есть ли сохраненные cookies
            cookies = await self._load_cookies_from_file()
            if cookies and not await self._are_cookies_expired(cookies):
                return cookies
            
            # Если cookies нет или они истекли, пытаемся получить новые
            new_cookies = await self._refresh_cookies()
            if new_cookies:
                await self._save_cookies_to_file(new_cookies)
                return new_cookies
            
            # Если не удалось получить новые cookies, возвращаем существующие (даже если они истекли)
            return cookies
            
        except Exception as e:
            self.logger.error(f"Error getting Fragment cookies: {e}")
            # Возвращаем существующие cookies в случае ошибки
            cookies = await self._load_cookies_from_file()
            return cookies
    
    async def _load_cookies_from_file(self) -> Optional[str]:
        """Загрузка cookies из файла"""
        try:
            if self.cookies_file.exists():
                with open(self.cookies_file, 'r') as f:
                    data = json.load(f)
                    return data.get('cookies')
            return None
        except Exception as e:
            self.logger.error(f"Error loading cookies from file: {e}")
            return None
    
    async def _save_cookies_to_file(self, cookies: str) -> None:
        """Сохранение cookies в файл"""
        try:
            # Создаем родительские директории, если они не существуют
            self.cookies_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'cookies': cookies,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'expires_at': (datetime.now(timezone.utc) + timedelta(seconds=self.cookie_refresh_interval)).isoformat()
            }
            with open(self.cookies_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            self.logger.error(f"Error saving cookies to file: {e}")
    
    async def _are_cookies_expired(self, cookies: str) -> bool:
        """Проверка, истекли ли cookies"""
        try:
            if self.cookies_file.exists():
                with open(self.cookies_file, 'r') as f:
                    data = json.load(f)
                    expires_at = data.get('expires_at')
                    if expires_at:
                        expires_datetime = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                        return datetime.now(timezone.utc) >= expires_datetime
            return True
        except Exception as e:
            self.logger.error(f"Error checking cookie expiration: {e}")
            return True
    
    async def _refresh_cookies(self) -> Optional[str]:
        """Обновление cookies через headless browser"""
        if not SELENIUM_AVAILABLE:
            self.logger.warning("Selenium not available, cannot refresh cookies automatically")
            return None
            
        try:
            self.logger.info("Refreshing Fragment cookies...")
            
            # Настройка headless браузера
            if not SELENIUM_AVAILABLE:
                self.logger.error("Selenium not available")
                return None

            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")

            # Используем удаленный Selenium сервер
            selenium_host = os.getenv("SELENIUM_HOST", "selenium-chrome")
            selenium_port = os.getenv("SELENIUM_PORT", "4444")
            selenium_url = f"http://{selenium_host}:{selenium_port}/wd/hub"
            
            try:
                # Удаленный драйвер с headless режимом
                driver = webdriver.Remote(
                    command_executor=selenium_url,
                    options=chrome_options
                )
                self.logger.info(f"Connected to remote Selenium server at {selenium_url}")
            except Exception as e:
                self.logger.error(f"Failed to connect to remote Selenium server: {e}")
                # Fallback: попытка использовать локальный chromedriver если удаленный недоступен
                try:
                    if CHROMEDRIVER_PY_AVAILABLE and binary_path:
                        service = ChromeService(executable_path=binary_path)
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                    else:
                        driver_path = os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
                        service = ChromeService(executable_path=driver_path)
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                    self.logger.warning("Using local Chrome driver as fallback")
                except Exception as fallback_error:
                    self.logger.error(f"Failed to create local Chrome driver: {fallback_error}")
                    return None

            try:
                # Переходим на страницу Fragment
                driver.get("https://fragment.com")

                # Ждем загрузки страницы
                wait = WebDriverWait(driver, 10)
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                
                # Здесь должна быть логика авторизации
                # Это упрощенный пример - в реальном приложении нужно реализовать
                # полную процедуру авторизации через Telegram
                
                # Получаем cookies
                selenium_cookies = driver.get_cookies()
                
                # Преобразуем cookies в формат Header String
                cookies_string = "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in selenium_cookies])
                
                self.logger.info("Successfully refreshed Fragment cookies")
                return cookies_string
                
            finally:
                driver.quit()
                
        except Exception as e:
            self.logger.error(f"Error refreshing Fragment cookies: {e}")
            return None
    
    async def validate_cookies(self, cookies: str) -> bool:
        """Валидация cookies через тестовый запрос к Fragment API"""
        # Сохраняем текущие cookies
        original_cookies = self.fragment_service.fragment_cookies
        
        try:
            # Устанавливаем новые cookies для теста
            self.fragment_service.fragment_cookies = cookies
            
            # Пытаемся получить информацию о тестовом пользователе
            result = await self.fragment_service.get_user_info("@fragment")
            
            return result["status"] == "success"
            
        except Exception as e:
            self.logger.error(f"Error validating Fragment cookies: {e}")
            return False
        finally:
            # Всегда восстанавливаем оригинальные cookies
            self.fragment_service.fragment_cookies = original_cookies


# Функция для интеграции в основное приложение
async def initialize_fragment_cookies(fragment_service: FragmentService) -> None:
    """
    Инициализация Fragment cookies при запуске приложения
    """
    if not os.getenv("FRAGMENT_AUTO_COOKIE_REFRESH", "False").lower() == "true":
        logging.info("Automatic Fragment cookie refresh is disabled")
        return
    
    try:
        cookie_manager = FragmentCookieManager(fragment_service)
        cookies = await cookie_manager.get_fragment_cookies()
        
        if cookies:
            fragment_service.fragment_cookies = cookies
            logging.info("Fragment cookies initialized successfully")
        else:
            logging.warning("Failed to initialize Fragment cookies")
            
    except Exception as e:
        logging.error(f"Error initializing Fragment cookies: {e}")