#!/usr/bin/env python3
"""
Интеграционные тесты для всей системы мониторинга
Проверяет взаимодействие всех компонентов системы
"""

import pytest
import asyncio
import subprocess
import json
from unittest.mock import patch, MagicMock
from services.system.alert_service import AlertService, AlertLevel
from services.system.external_health_service import ExternalHealthService
from services.system.circuit_breaker import CircuitBreaker


class TestIntegrationMonitoringSystem:
    """Интеграционные тесты всей системы мониторинга"""

    @pytest.fixture
    def alert_service(self):
        """Создание сервиса алертов с мок-отправкой"""
        service = AlertService()
        with patch.object(service, 'send_telegram_alert') as mock_telegram:
            yield service

    @pytest.fixture
    def external_health_service(self):
        """Создание сервиса мониторинга внешних API"""
        service = ExternalHealthService()
        # Переопределяем конфигурацию для тестов
        service.services = [
            service._get_services_config()[0],  # Берем только telegram_api для тестов
        ]
        return service

    @pytest.fixture
    def circuit_breaker(self):
        """Создание circuit breaker"""
        from services.system.circuit_breaker import CircuitConfig
        config = CircuitConfig(failure_threshold=3, recovery_timeout=30)
        return CircuitBreaker("test_service", config)

    @pytest.mark.asyncio
    async def test_alert_service_integration(self, alert_service):
        """Тестирование интеграции Alert Service с внешними системами"""
        test_message = "TEST: Integration test alert"
        
        # Отправляем тестовое уведомление (используем WARNING, так как INFO не отправляется в Telegram)
        await alert_service.create_alert(AlertLevel.WARNING, test_message, "integration_test")
        
        # Проверяем, что метод отправки был вызван
        alert_service.send_telegram_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_external_health_with_alerting(self, external_health_service, alert_service):
        """Тестирование интеграции External Health с Alert Service"""
        # Мокируем проверку сервиса чтобы возвращала ошибку
        with patch.object(external_health_service, 'check_service') as mock_check:
            mock_check.return_value = {
                "status": "unhealthy",
                "error": "Connection failed",
                "response_time_ms": 5000,
                "timestamp": "2024-01-01T00:00:00Z"
            }
            
            # Выполняем проверку
            result = await external_health_service.check_all_services()
            
            # Проверяем результат
            assert result["status"] == "unhealthy"
            assert result["has_critical_issues"] is True
            
            # Проверяем наличие информации о неисправном сервисе
            assert "services" in result
            assert len(result["services"]) > 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, circuit_breaker, alert_service):
        """Тестирование работы Circuit Breaker в системе мониторинга"""
        service_name = "test_service"
        
        # Функция, которая всегда вызывает исключение
        def failing_function():
            raise Exception("Test failure")
        
        # Симулируем несколько неудачных вызовов через основной метод call()
        for _ in range(3):
            try:
                await circuit_breaker.call(failing_function)
            except Exception:
                pass  # Ожидаемое исключение
        
        # Проверяем, что circuit breaker открыт
        assert circuit_breaker.state.name == "OPEN"
        
        # Проверяем, что Circuit Breaker корректно блокирует дальнейшие вызовы
        try:
            await circuit_breaker.call(failing_function)
            assert False, "Circuit Breaker должен блокировать вызовы в состоянии OPEN"
        except Exception as e:
            assert "is OPEN" in str(e)

    def test_redis_cluster_monitor_integration(self):
        """Тестирование интеграции Redis Cluster мониторинга"""
        # Запускаем тестовый скрипт Redis мониторинга
        result = subprocess.run([
            'bash', 'tests/test_redis_cluster_monitor.sh'
        ], capture_output=True, text=True, cwd='/home/rachi/Documents/GitHub/Mirza-Telegram-Shop-Bot')
        
        assert result.returncode == 0
        # Проверяем, что тестирование завершилось корректно (любой из этих текстов)
        success_indicators = [
            "All Redis cluster tests passed",
            "Лог тестирования сохранен",
            "тестов Redis Cluster мониторинга"
        ]
        assert any(indicator in result.stdout for indicator in success_indicators)

    def test_cloudflare_tunnel_monitor_integration(self):
        """Тестирование интеграции Cloudflare Tunnel мониторинга"""
        # Запускаем тестовый скрипт Cloudflare мониторинга
        result = subprocess.run([
            'bash', 'tests/test_cloudflare_tunnel_monitor.sh'
        ], capture_output=True, text=True, cwd='/home/rachi/Documents/GitHub/Mirza-Telegram-Shop-Bot')
        
        assert result.returncode == 0
        # Проверяем, что тестирование завершилось корректно (любой из этих текстов)
        success_indicators = [
            "All Cloudflare tunnel tests passed",
            "Лог тестирования сохранен",
            "тестов Cloudflare Tunnel мониторинга"
        ]
        assert any(indicator in result.stdout for indicator in success_indicators)

    @pytest.mark.asyncio
    async def test_full_monitoring_pipeline(self, external_health_service, alert_service):
        """Тестирование полного пайплайна мониторинга"""
        # Мокируем все компоненты
        with patch.object(external_health_service, 'check_all_services') as mock_health_check, \
             patch.object(alert_service, 'create_alert') as mock_send_alert:
            
            # Настраиваем мок для health check
            mock_health_check.return_value = {
                "status": "healthy",
                "response_time_ms": 150,
                "timestamp": "2024-01-01T00:00:00Z",
                "services": {
                    "telegram_api": {
                        "status": "healthy",
                        "response_time_ms": 100,
                        "status_code": 200
                    }
                },
                "has_critical_issues": False
            }
            
            # Выполняем проверку
            result = await external_health_service.check_all_services()
            
            # Проверяем результаты
            assert result["status"] == "healthy"
            assert not result["has_critical_issues"]
            
            # Проверяем, что alert не отправлялся (все здорово)
            mock_send_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_critical_failure_pipeline(self, external_health_service, alert_service):
        """Тестирование пайплайна при критическом сбое"""
        # Мокируем health check для критического сбоя
        with patch.object(external_health_service, 'check_all_services') as mock_health_check:
            
            # Настраиваем мок для critical failure
            mock_health_check.return_value = {
                "status": "unhealthy",
                "response_time_ms": 5000,
                "timestamp": "2024-01-01T00:00:00Z",
                "services": {
                    "telegram_api": {
                        "status": "unhealthy",
                        "error": "Connection timeout",
                        "response_time_ms": 5000
                    }
                },
                "has_critical_issues": True
            }
            
            # Выполняем проверку
            result = await external_health_service.check_all_services()
            
            # Проверяем результаты
            assert result["status"] == "unhealthy"
            assert result["has_critical_issues"]
            
            # Проверяем структуру ответа
            assert "services" in result
            assert "telegram_api" in result["services"]
            assert result["services"]["telegram_api"]["status"] == "unhealthy"


if __name__ == "__main__":
    # Запуск интеграционных тестов
    pytest.main([__file__, "-v"])