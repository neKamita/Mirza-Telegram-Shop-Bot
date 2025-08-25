#!/usr/bin/env python3
"""
Скрипт предварительной проверки настроек Fragment API
Запускается перед основным приложением для проверки критических настроек
"""
import os
import sys
import asyncio
import logging
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Импортируем FragmentService для проверки подключения
from services.fragment.fragment_service import FragmentService


def setup_logging():
    """Настройка логирования"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def check_seed_phrase_format(seed_phrase: str) -> bool:
    """Проверка формата seed phrase"""
    if not seed_phrase:
        print("❌ FRAGMENT_SEED_PHRASE не задана в переменных окружения")
        return False
    
    # Проверяем значение по умолчанию
    if seed_phrase == "your_24_words_seed_phrase" or seed_phrase == "your_24_words_seed_phrase_from_ton_v4r2_wallet":
        print("❌ FRAGMENT_SEED_PHRASE содержит значение по умолчанию. Пожалуйста, укажите реальную seed phrase.")
        return False
    
    # Проверяем количество слов
    words = seed_phrase.strip().split()
    if len(words) != 24:
        print(f"❌ Неправильный формат FRAGMENT_SEED_PHRASE: ожидается 24 слова, получено {len(words)}")
        return False
    
    print(f"✅ Seed phrase имеет правильный формат ({len(words)} слов)")
    return True


def check_fragment_cookies(cookies: str) -> bool:
    """Проверка формата cookies"""
    if not cookies:
        print("⚠️  FRAGMENT_COOKIES не заданы в переменных окружения")
        print("💡 Cookies необходимы для авторизации в Fragment API")
        return False
    
    # Проверяем значение по умолчанию
    if cookies == "your_fragment_cookies" or cookies == "your_fragment_cookies_from_cookie_editor_extension":
        print("❌ FRAGMENT_COOKIES содержат значение по умолчанию. Пожалуйста, укажите реальные cookies.")
        return False
    
    print("✅ Cookies заданы")
    return True


def check_auto_refresh_setting() -> bool:
    """Проверка настройки автоматического обновления"""
    auto_refresh = os.getenv("FRAGMENT_AUTO_COOKIE_REFRESH", "False").lower() == "true"
    if auto_refresh:
        print("✅ Автоматическое обновление cookies включено")
    else:
        print("⚠️  Автоматическое обновление cookies отключено")
        print("💡 Рекомендуется включить FRAGMENT_AUTO_COOKIE_REFRESH=true для непрерывной работы")
    
    return True


def check_chrome_driver() -> bool:
    """Проверка наличия ChromeDriver"""
    driver_path = os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
    if os.path.exists(driver_path):
        print("✅ ChromeDriver найден")
        return True
    else:
        # Проверяем, установлен ли webdriver-manager для автоматического управления ChromeDriver
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            print("✅ ChromeDriver доступен через webdriver-manager")
            return True
        except ImportError:
            print("⚠️  ChromeDriver не найден по пути:", driver_path)
            print("⚠️  webdriver-manager не установлен")
            print("💡 Это может повлиять на автоматическое обновление cookies")
            print("💡 Установите webdriver-manager: pip install webdriver-manager")
            return False


def check_environment_variables() -> bool:
    """Проверка всех необходимых переменных окружения"""
    print("🔍 Проверка переменных окружения Fragment API...")
    print("-" * 50)
    
    all_checks_passed = True
    
    # Проверка seed phrase
    seed_phrase = os.getenv("FRAGMENT_SEED_PHRASE", "")
    if not check_seed_phrase_format(seed_phrase):
        all_checks_passed = False
    
    # Проверка cookies
    cookies = os.getenv("FRAGMENT_COOKIES", "")
    if not check_fragment_cookies(cookies):
        # Это не критично для запуска, но предупреждаем
        pass
    
    # Проверка автообновления
    if not check_auto_refresh_setting():
        all_checks_passed = False
    
    # Проверка ChromeDriver
    if not check_chrome_driver():
        # Это не критично для запуска, но предупреждаем
        pass
    
    print("-" * 50)
    
    if all_checks_passed:
        print("✅ Все критические проверки пройдены")
        return True
    else:
        print("❌ Некоторые проверки не пройдены")
        return False


async def check_fragment_api_connectivity() -> bool:
    """Проверка подключения к Fragment API"""
    print("\n📡 Проверка подключения к Fragment API...")
    print("-" * 40)
    
    try:
        fragment_service = FragmentService()
        
        # Проверка ping
        print("Проверка ping...")
        ping_result = await fragment_service.ping()
        if ping_result["status"] == "success":
            print("✅ Fragment API доступен")
        else:
            print(f"⚠️  Fragment API недоступен: {ping_result.get('error', 'Unknown error')}")
        
        # Проверка seed phrase (если она правильная)
        if fragment_service.seed_phrase and len(fragment_service.seed_phrase.strip().split()) == 24:
            print("Проверка баланса...")
            balance_result = await fragment_service.get_balance()
            if balance_result["status"] == "success":
                balance_data = balance_result.get("result", {})
                print(f"✅ Баланс доступен: {balance_data.get('balance', 'N/A')} {balance_data.get('currency', 'TON')}")
            else:
                print(f"⚠️  Не удалось получить баланс: {balance_result.get('error', 'Unknown error')}")
        else:
            print("⚠️  Пропуск проверки баланса из-за неправильной seed phrase")
        
        print("-" * 40)
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при проверке Fragment API: {e}")
        return False


async def main():
    """Основная функция"""
    logger = setup_logging()
    
    print("🚀 Предварительная проверка настроек Fragment API")
    print("=" * 50)
    
    # Проверка переменных окружения
    env_check_passed = check_environment_variables()
    
    # Проверка подключения к API (если критические настройки верны)
    if env_check_passed:
        await check_fragment_api_connectivity()
    
    print("\n📋 Резюме:")
    print("-" * 20)
    
    if env_check_passed:
        print("✅ Все критические настройки корректны")
        print("🚀 Можно запускать основное приложение")
        sys.exit(0)
    else:
        print("❌ Обнаружены критические ошибки в настройках")
        print("💡 Пожалуйста, исправьте ошибки перед запуском приложения")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())