#!/usr/bin/env python3
"""
Тесты для External Health Service - проверка мониторинга внешних API
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.system.external_health_service import (
    ExternalHealthService,
    ExternalServiceConfig,
    external_health_service
)


class TestExternalHealthService:
    """Тесты для External Health Service"""

    @pytest.fixture
    def mock_service(self):
        """Создание mock сервиса с тестовой конфигурацией"""
        service = ExternalHealthService()
        # Переопределяем конфигурацию для тестов
        service.services = [
            ExternalServiceConfig(
                name="test_service_1",
                url="https://httpbin.org/status/200",
                timeout=2,
                expected_status=200,
                is_critical=True
            ),
            ExternalServiceConfig(
                name="test_service_2", 
                url="https://httpbin.org/status/404",
                timeout=2,
                expected_status=404,
                is_critical=False
            ),
            ExternalServiceConfig(
                name="test_service_timeout",
                url="https://httpbin.org/delay/5",  # Будет таймаут
                timeout=1,
                expected_status=200,
                is_critical=True
            )
        ]
        return service

    @pytest.mark.asyncio
    async def test_service_configuration(self, mock_service):
        """Тестирование конфигурации сервисов"""
        config = mock_service.get_service_configuration()
        
        assert len(config) == 3
        assert config[0]["name"] == "test_service_1"
        assert config[0]["is_critical"] is True
        assert config[1]["name"] == "test_service_2"
        assert config[1]["is_critical"] is False

    @pytest.mark.asyncio
    async def test_check_service_success(self, mock_service):
        """Тестирование успешной проверки сервиса"""
        service_config = mock_service.services[0]
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_get.return_value.__aenter__.return_value = mock_response
            
            result = await mock_service.check_service(service_config)
            
            assert result["status"] == "healthy"
            assert result["status_code"] == 200
            assert "response_time_ms" in result

    @pytest.mark.asyncio
    async def test_check_service_wrong_status(self, mock_service):
        """Тестирование проверки сервиса с неправильным статусом"""
        service_config = mock_service.services[1]  # Ожидает 404, получит 200
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status = 200  # Неправильный статус
            mock_get.return_value.__aenter__.return_value = mock_response
            
            result = await mock_service.check_service(service_config)
            
            assert result["status"] == "unhealthy"
            assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_check_service_timeout(self, mock_service):
        """Тестирование таймаута при проверке сервиса"""
        service_config = mock_service.services[2]  # Сервис с таймаутом
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_get.side_effect = asyncio.TimeoutError()
            
            result = await mock_service.check_service(service_config)
            
            assert result["status"] == "unhealthy"
            assert result["error"] == "Timeout"
            assert result["response_time_ms"] == 1000  # 1 секунда таймаут

    @pytest.mark.asyncio
    async def test_check_service_exception(self, mock_service):
        """Тестирование исключения при проверке сервиса"""
        service_config = mock_service.services[0]
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_get.side_effect = Exception("Connection failed")
            
            result = await mock_service.check_service(service_config)
            
            assert result["status"] == "unhealthy"
            assert result["error"] == "Connection failed"

    @pytest.mark.asyncio
    async def test_check_all_services_healthy(self, mock_service):
        """Тестирование проверки всех сервисов (все здоровы)"""
        # Мокируем все проверки чтобы возвращали успешный результат
        with patch.object(mock_service, 'check_service') as mock_check:
            mock_check.return_value = {
                "status": "healthy",
                "status_code": 200,
                "response_time_ms": 100,
                "timestamp": "2024-01-01T00:00:00Z"
            }
            
            result = await mock_service.check_all_services()
            
            assert result["status"] == "healthy"
            assert result["has_critical_issues"] is False
            assert len(result["services"]) == 3

    @pytest.mark.asyncio
    async def test_check_all_services_critical_failure(self, mock_service):
        """Тестирование проверки всех сервисов (критический сбой)"""
        # Мокируем проверки: первый сервис (критический) падает
        with patch.object(mock_service, 'check_service') as mock_check:
            def side_effect(service):
                if service.name == "test_service_1":
                    return {
                        "status": "unhealthy",
                        "error": "Connection failed",
                        "response_time_ms": 100,
                        "timestamp": "2024-01-01T00:00:00Z"
                    }
                else:
                    return {
                        "status": "healthy",
                        "status_code": 200,
                        "response_time_ms": 100,
                        "timestamp": "2024-01-01T00:00:00Z"
                    }
            
            mock_check.side_effect = side_effect
            result = await mock_service.check_all_services()
            
            assert result["status"] == "unhealthy"
            assert result["has_critical_issues"] is True
            assert len(result["services"]) == 3
            assert result["services"]["test_service_1"]["status"] == "unhealthy"
