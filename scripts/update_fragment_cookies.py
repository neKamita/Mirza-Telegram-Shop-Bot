#!/usr/bin/env python3
"""
Скрипт для автоматического обновления Fragment cookies
Запускается при старте контейнера если включена настройка FRAGMENT_AUTO_COOKIE_REFRESH
"""
import os
import sys
import json
import time
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.fragment.fragment_cookie_manager import FragmentCookieManager
from services.fragment.fragment_service import FragmentService


def setup_logging():
    """Настройка логирования"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def update_fragment_cookies():
    """Обновление Fragment cookies"""
    logger = setup_logging()
    
    try:
        logger.info("Starting Fragment cookies update process...")
        
        # Проверяем, включено ли автоматическое обновление
        auto_refresh = os.getenv("FRAGMENT_AUTO_COOKIE_REFRESH", "False").lower() == "true"
        if not auto_refresh:
            logger.info("Automatic Fragment cookie refresh is disabled")
            return True
        
        # Создаем сервисы
        fragment_service = FragmentService()
        cookie_manager = FragmentCookieManager(fragment_service)
        
        # Получаем текущие cookies
        current_cookies = fragment_service.fragment_cookies
        logger.info(f"Current cookies status: {'present' if current_cookies else 'absent'}")
        
        # Проверяем, нужно ли обновить cookies
        if current_cookies:
            # Используем asyncio.run для выполнения асинхронного метода в синхронном контексте
            expired = asyncio.run(cookie_manager._are_cookies_expired(current_cookies))
            if not expired:
                logger.info("Current cookies are still valid, no update needed")
                return True
        
        # Обновляем cookies
        logger.info("Refreshing Fragment cookies...")
        new_cookies = asyncio.run(cookie_manager._refresh_cookies())
        
        if new_cookies:
            # Сохраняем новые cookies
            asyncio.run(cookie_manager._save_cookies_to_file(new_cookies))
            logger.info("Fragment cookies updated successfully")
            
            # Обновляем переменную окружения в runtime (если возможно)
            os.environ["FRAGMENT_COOKIES"] = new_cookies
            fragment_service.fragment_cookies = new_cookies
            
            return True
        else:
            logger.warning("Failed to refresh Fragment cookies")
            return False
            
    except Exception as e:
        logger.error(f"Error updating Fragment cookies: {e}")
        return False


def main():
    """Основная функция"""
    logger = setup_logging()
    
    try:
        logger.info("Fragment Cookie Update Script started")
        
        # Проверяем, запущены ли мы в Docker контейнере
        if Path("/.dockerenv").exists():
            logger.info("Running inside Docker container")
        else:
            logger.info("Running outside Docker container")
        
        # Обновляем cookies
        success = update_fragment_cookies()
        
        if success:
            logger.info("Fragment Cookie Update Script completed successfully")
            sys.exit(0)
        else:
            logger.error("Fragment Cookie Update Script failed")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Unexpected error in Fragment Cookie Update Script: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())