#!/usr/bin/env python3
"""
Скрипт для проверки состояния Fragment API и cookies
"""
import os
import sys
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.fragment_service import FragmentService
from services.fragment_cookie_manager import FragmentCookieManager


async def check_fragment_status():
    """Проверка состояния Fragment API"""
    print("🔍 Проверка состояния Fragment API...")
    
    try:
        # Создаем сервис
        fragment_service = FragmentService()
        
        # Проверяем ping
        print("\n📡 Проверка ping...")
        ping_result = await fragment_service.ping()
        if ping_result["status"] == "success":
            print("   ✅ Fragment API доступен")
        else:
            print(f"   ❌ Fragment API недоступен: {ping_result.get('error', 'Unknown error')}")
        
        # Проверяем seed phrase
        print("\n🔐 Проверка seed phrase...")
        if fragment_service.seed_phrase:
            # Простая проверка формата
            words = fragment_service.seed_phrase.strip().split()
            if len(words) == 24:
                print("   ✅ Seed phrase корректна (24 слова)")
            else:
                print(f"   ⚠️  Seed phrase имеет неправильный формат ({len(words)} слов)")
        else:
            print("   ❌ Seed phrase не задана")
        
        # Проверяем cookies
        print("\n🍪 Проверка cookies...")
        if fragment_service.fragment_cookies:
            print("   ✅ Cookies заданы")
            
            # Проверяем через менеджер
            cookie_manager = FragmentCookieManager(fragment_service)
            expired = await cookie_manager._are_cookies_expired(fragment_service.fragment_cookies)
            if not expired:
                print("   ✅ Cookies действительны")
            else:
                print("   ⚠️  Cookies истекли")
        else:
            print("   ❌ Cookies не заданы")
        
        # Проверяем баланс (если возможно)
        print("\n💰 Проверка баланса...")
        if fragment_service.seed_phrase and len(fragment_service.seed_phrase.strip().split()) == 24:
            balance_result = await fragment_service.get_balance()
            if balance_result["status"] == "success":
                balance_data = balance_result.get("result", {})
                print(f"   ✅ Баланс: {balance_data.get('balance', 'N/A')} {balance_data.get('currency', 'TON')}")
            else:
                print(f"   ⚠️  Не удалось получить баланс: {balance_result.get('error', 'Unknown error')}")
        else:
            print("   ⚠️  Невозможно проверить баланс без корректной seed phrase")
        
        print("\n✅ Проверка завершена!")
        
    except Exception as e:
        print(f"\n❌ Ошибка при проверке Fragment API: {e}")
        return False
    
    return True


if __name__ == "__main__":
    import asyncio
    asyncio.run(check_fragment_status())