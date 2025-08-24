#!/usr/bin/env python3
"""
Скрипт для тестирования Fragment ChromeDriver интеграции
"""
import asyncio
import logging
import os
from pathlib import Path

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_chromedriver_availability():
    """Тестирование доступности ChromeDriver"""
    try:
        from services.infrastructure.fragment_cookie_manager import FragmentCookieManager
        from services.fragment.fragment_service import FragmentService

        logger.info("Тестирование доступности ChromeDriver...")

        # Проверяем наличие необходимых переменных окружения
        if not os.getenv("FRAGMENT_AUTO_COOKIE_REFRESH", "False").lower() == "true":
            logger.warning("FRAGMENT_AUTO_COOKIE_REFRESH не установлен в true, пропускаем тест ChromeDriver")
            return False

        # Создаем сервисы
        fragment_service = FragmentService()
        cookie_manager = FragmentCookieManager(fragment_service)

        # Проверяем доступность selenium и webdriver-manager
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service as ChromeService
            from webdriver_manager.chrome import ChromeDriverManager

            logger.info("Selenium и webdriver-manager доступны")

            # Настройка headless браузера для тестирования
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")

            # Пытаемся создать драйвер
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)

            # Простой тест - открываем страницу
            driver.get("https://www.google.com")
            title = driver.title
            driver.quit()

            logger.info(f"ChromeDriver работает корректно, заголовок страницы: {title}")
            return True

        except Exception as e:
            logger.error(f"Ошибка при тестировании ChromeDriver: {e}")
            return False

    except Exception as e:
        logger.error(f"Ошибка при инициализации тестирования: {e}")
        return False

async def main():
    """Основная функция тестирования"""
    logger.info("=== Тестирование Fragment ChromeDriver интеграции ===")

    success = await test_chromedriver_availability()

    if success:
        logger.info("✅ Fragment ChromeDriver интеграция работает корректно")
    else:
        logger.error("❌ Fragment ChromeDriver интеграция имеет проблемы")

    return success

if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)