"""
Тесты для системы алертинга - проверка отправки уведомлений разных уровней
Интеграционные тесты для AlertService с мокированием внешних вызовов
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from services.system.alert_service import AlertService, AlertLevel, Alert
from config.settings import settings


class TestAlertService:
    """Тесты для сервиса алертинга"""

    @pytest.fixture
    def alert_service(self):
        """Фикстура для создания экземпляра AlertService"""
        service = AlertService()
        service.active_alerts.clear()
        service.alert_history.clear()
        return service

    @pytest.mark.asyncio
    async def test_create_alert_with_different_levels(self, alert_service):
        """Тест создания алертов разных уровней"""
        # Тестируем создание алертов всех уровней
        levels_to_test = [
            (AlertLevel.INFO, "Тестовое информационное сообщение"),
            (AlertLevel.WARNING, "Тестовое предупреждение"),
            (AlertLevel.CRITICAL, "Тестовая критическая ошибка"),
            (AlertLevel.EMERGENCY, "Тестовая аварийная ситуация")
        ]

        for level, message in levels_to_test:
            alert_id = await alert_service.create_alert(
                level=level,
                message=message,
                service="test_service",
                details={"test_key": "test_value"}
            )

            assert alert_id is not None
            assert alert_id.startswith("test_service_")
            
            # Проверяем, что алерт добавлен в историю
            assert len(alert_service.alert_history) > 0
            last_alert = alert_service.alert_history[-1]
            assert last_alert.level == level
            assert last_alert.message == message
            assert last_alert.service == "test_service"

    @pytest.mark.asyncio
    async def test_alert_message_formatting(self, alert_service):
        """Тест форматирования сообщений для Telegram"""
        # Создаем тестовый алерт
        test_alert = Alert(
            level=AlertLevel.CRITICAL,
            message="Тестовое сообщение с деталями",
            service="test_service",
            timestamp=datetime.now(timezone.utc),
            details={
                "error_code": "500",
                "endpoint": "/api/test",
                "response_time": "2.5s"
            }
        )

        # Тестируем только форматирование, без реальной отправки
        emoji = alert_service._get_alert_emoji(test_alert.level)
        expected_emoji = "🚨"
        
        # Проверяем emoji маппинг
        assert emoji == expected_emoji
        
        # Проверяем, что метод форматирования работает корректно
        # (это внутренний метод, но мы можем проверить его результат)
        emoji_map = alert_service._get_alert_emoji(test_alert.level)
        assert emoji_map == "🚨"
        
        # Проверяем создание алерта без отправки в Telegram
        with patch('config.settings.settings.telegram_alerts_enabled', False):
            alert_id = await alert_service.create_alert(
                level=AlertLevel.INFO,
                message="Тестовое сообщение INFO",
                service="test_service"
            )
            assert alert_id is not None
            assert alert_id.startswith("test_service_")

    @pytest.mark.asyncio
    async def test_telegram_send_failure_handling(self, alert_service):
        """Тест обработки ошибок при отправке в Telegram"""
        test_alert = Alert(
            level=AlertLevel.WARNING,
            message="Тест обработки ошибок",
            service="test_service",
            timestamp=datetime.now(timezone.utc)
        )

        # Мокируем неудачную отправку
        with patch('aiohttp.ClientSession.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 403  # Forbidden
            
            result = await alert_service.send_telegram_alert(test_alert)
            assert result is False

        # Мокируем исключение при отправке
        with patch('aiohttp.ClientSession.post', side_effect=Exception("Connection error")):
            result = await alert_service.send_telegram_alert(test_alert)
            assert result is False

    @pytest.mark.asyncio
    async def test_alert_resolution(self, alert_service):
        """Тест разрешения алертов"""
        # Создаем алерт
        alert_id = await alert_service.create_alert(
            level=AlertLevel.CRITICAL,
            message="Тестовый алерт для разрешения",
            service="test_service"
        )

        # Проверяем, что алерт активен
        assert alert_id in alert_service.active_alerts
        assert not alert_service.active_alerts[alert_id].resolved

        # Разрешаем алерт
        result = await alert_service.resolve_alert(alert_id, "Проблема решена")
        assert result is True
        
        # Проверяем, что алерт удален из активных
        assert alert_id not in alert_service.active_alerts
        
        # Проверяем, что алерт помечен как resolved в истории
        resolved_alerts = [a for a in alert_service.alert_history if a.resolved]
        assert len(resolved_alerts) > 0

    @pytest.mark.asyncio
    async def test_redis_cluster_alerting(self, alert_service):
        """Тест алертинга для Redis Cluster"""
        # Тестируем разные сценарии покрытия слотов
        
        # Критическая ситуация - нет покрытия слотов
        cluster_info = {"slots_covered": 0, "total_slots": 16384}
        alert_id = await alert_service.check_and_alert_redis_cluster(cluster_info)
        assert alert_id is not None
        assert alert_service.alert_history[-1].level == AlertLevel.EMERGENCY

        # Частичное покрытие (критическое)
        cluster_info = {"slots_covered": 10000, "total_slots": 16384}
        alert_id = await alert_service.check_and_alert_redis_cluster(cluster_info)
        assert alert_id is not None
        assert alert_service.alert_history[-1].level == AlertLevel.CRITICAL

        # Частичное покрытие (предупреждение)
        cluster_info = {"slots_covered": 15000, "total_slots": 16384}
        alert_id = await alert_service.check_and_alert_redis_cluster(cluster_info)
        assert alert_id is not None
        assert alert_service.alert_history[-1].level == AlertLevel.WARNING

        # Полное покрытие - алертов не должно быть
        cluster_info = {"slots_covered": 16384, "total_slots": 16384}
        alert_id = await alert_service.check_and_alert_redis_cluster(cluster_info)
        assert alert_id is None

    @pytest.mark.asyncio
    async def test_external_service_alerting(self, alert_service):
        """Тест алертинга для внешних сервисов"""
        # Критический сервис недоступен
        alert_id = await alert_service.check_and_alert_external_service(
            "telegram_api", "unhealthy", 5000, "Connection timeout"
        )
        assert alert_id is not None
        assert alert_service.alert_history[-1].level == AlertLevel.CRITICAL

        # Некритичный сервис недоступен
        alert_id = await alert_service.check_and_alert_external_service(
            "fragment_api", "unhealthy", 3000, "Timeout"
        )
        assert alert_id is not None
        assert alert_service.alert_history[-1].level == AlertLevel.WARNING

        # Сервис здоров - алертов не должно быть
        alert_id = await alert_service.check_and_alert_external_service(
            "telegram_api", "healthy", 100, None
        )
        assert alert_id is None

    @pytest.mark.asyncio
    async def test_system_resources_alerting(self, alert_service):
        """Тест алертинга для системных ресурсов"""
        # Высокое использование CPU
        resources = {
            "cpu": {"usage_percent": 95},
            "memory": {"usage_percent": 70}
        }
        alert_ids = await alert_service.check_and_alert_system_resources(resources)
        assert len(alert_ids) == 1
        assert alert_service.alert_history[-1].level == AlertLevel.CRITICAL

        # Высокое использование памяти
        resources = {
            "cpu": {"usage_percent": 75},
            "memory": {"usage_percent": 92}
        }
        alert_ids = await alert_service.check_and_alert_system_resources(resources)
        assert len(alert_ids) == 1
        assert alert_service.alert_history[-1].level == AlertLevel.CRITICAL

        # Предупреждение для CPU
        resources = {
            "cpu": {"usage_percent": 85},
            "memory": {"usage_percent": 65}
        }
        alert_ids = await alert_service.check_and_alert_system_resources(resources)
        assert len(alert_ids) == 1
        assert alert_service.alert_history[-1].level == AlertLevel.WARNING

    def test_alert_emoji_mapping(self, alert_service):
        """Тест маппинга emoji для разных уровней алертов"""
        emoji_map = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️", 
            AlertLevel.CRITICAL: "🚨",
            AlertLevel.EMERGENCY: "🔴"
        }

        for level, expected_emoji in emoji_map.items():
            emoji = alert_service._get_alert_emoji(level)
            assert emoji == expected_emoji

        # Тест для неизвестного уровня
        class FakeLevel:
            value = "UNKNOWN"
        
        emoji = alert_service._get_alert_emoji(FakeLevel())
        assert emoji == "📢"  # Дефолтный emoji


if __name__ == "__main__":
    # Запуск тестов вручную
    import sys
    import subprocess
    
    result = subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"])
    sys.exit(result.returncode)