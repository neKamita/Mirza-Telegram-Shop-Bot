#!/usr/bin/env python3
"""
Скрипт для периодического обновления Fragment cookies во время работы приложения
Запускается как фоновая задача и обновляет cookies по расписанию
"""
import os
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.fragment.fragment_service import FragmentService
from services.fragment.fragment_cookie_manager import FragmentCookieManager


class FragmentCookieRefresher:
    """Периодический обновлятор Fragment cookies"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.fragment_service = FragmentService()
        self.cookie_manager = FragmentCookieManager(self.fragment_service)
        self.interval = int(os.getenv("FRAGMENT_COOKIE_REFRESH_INTERVAL", "3600"))  # 1 час по умолчанию
        self.running = False
        
    async def start(self):
        """Запуск периодического обновления"""
        self.logger.info(f"Starting Fragment Cookie Refresher with interval {self.interval} seconds")
        self.running = True
        
        while self.running:
            try:
                await self._refresh_cookies_if_needed()
                await asyncio.sleep(self.interval)
            except Exception as e:
                self.logger.error(f"Error in Fragment Cookie Refresher: {e}")
                await asyncio.sleep(60)  # Ждем 1 минуту перед повторной попыткой
    
    async def stop(self):
        """Остановка периодического обновления"""
        self.logger.info("Stopping Fragment Cookie Refresher")
        self.running = False
    
    async def _refresh_cookies_if_needed(self):
        """Обновление cookies при необходимости"""
        try:
            self.logger.info("Checking Fragment cookies expiration...")
            
            # Проверяем, есть ли сохраненные cookies
            current_cookies = await self.cookie_manager._load_cookies_from_file()
            if not current_cookies:
                self.logger.info("No saved cookies found, refreshing...")
                await self._refresh_cookies()
                return
            
            # Проверяем, истекли ли cookies
            expired = await self.cookie_manager._are_cookies_expired(current_cookies)
            if expired:
                self.logger.info("Fragment cookies expired, refreshing...")
                await self._refresh_cookies()
            else:
                self.logger.info("Fragment cookies are still valid")
                
        except Exception as e:
            self.logger.error(f"Error checking Fragment cookies: {e}")
    
    async def _refresh_cookies(self):
        """Обновление cookies"""
        try:
            # Обновляем cookies
            new_cookies = await self.cookie_manager._refresh_cookies()
            
            if new_cookies:
                # Сохраняем новые cookies
                await self.cookie_manager._save_cookies_to_file(new_cookies)
                
                # Обновляем переменные в сервисе
                self.fragment_service.fragment_cookies = new_cookies
                os.environ["FRAGMENT_COOKIES"] = new_cookies
                
                self.logger.info("Fragment cookies refreshed successfully")
            else:
                self.logger.warning("Failed to refresh Fragment cookies")
                
        except Exception as e:
            self.logger.error(f"Error refreshing Fragment cookies: {e}")


async def main():
    """Основная функция"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    # Проверяем, включено ли автоматическое обновление
    auto_refresh = os.getenv("FRAGMENT_AUTO_COOKIE_REFRESH", "False").lower() == "true"
    if not auto_refresh:
        logger.info("Automatic Fragment cookie refresh is disabled")
        return
    
    try:
        logger.info("Fragment Cookie Refresher started")
        
        # Создаем и запускаем обновлятор
        refresher = FragmentCookieRefresher()
        await refresher.start()
        
    except KeyboardInterrupt:
        logger.info("Fragment Cookie Refresher interrupted")
    except Exception as e:
        logger.error(f"Unexpected error in Fragment Cookie Refresher: {e}")
    finally:
        logger.info("Fragment Cookie Refresher stopped")


if __name__ == "__main__":
    asyncio.run(main())