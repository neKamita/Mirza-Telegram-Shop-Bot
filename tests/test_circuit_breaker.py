"""
Тесты для Circuit Breaker паттерна
"""
import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from services.system.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitConfig,
    CircuitBreakerManager,
    CircuitConfigs
)


class TestCircuitBreaker:
    """Тесты для CircuitBreaker"""

    def test_initial_state_closed(self):
        """Тест начального состояния CLOSED"""
        circuit = CircuitBreaker("test_service", CircuitConfig())
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0

    @pytest.mark.asyncio
    async def test_call_success_closed_state(self):
        """Тест успешного вызова в состоянии CLOSED"""
        circuit = CircuitBreaker("test_service", CircuitConfig())
        mock_func = AsyncMock(return_value="success")
        
        result = await circuit.call(mock_func)
        
        assert result == "success"
        assert circuit.state == CircuitState.CLOSED
        assert circuit.success_count == 1

    @pytest.mark.asyncio
    async def test_call_failure_trips_to_open(self):
        """Тест перехода в OPEN состояние после нескольких неудач"""
        circuit = CircuitBreaker("test_service", CircuitConfig(failure_threshold=2))
        mock_func = AsyncMock(side_effect=Exception("Service down"))
        
        # Первая неудача
        with pytest.raises(Exception):
            await circuit.call(mock_func)
        
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 1
        
        # Вторая неудача - должно перейти в OPEN
        with pytest.raises(Exception):
            await circuit.call(mock_func)
        
        assert circuit.state == CircuitState.OPEN
        assert circuit.failure_count == 2

    @pytest.mark.asyncio
    async def test_call_rejects_when_open(self):
        """Тест отклонения вызовов в состоянии OPEN"""
        circuit = CircuitBreaker("test_service", CircuitConfig(failure_threshold=1))
        circuit.state = CircuitState.OPEN
        circuit.last_failure_time = time.time()
        
        mock_func = AsyncMock(return_value="success")
        
        with pytest.raises(Exception, match="Circuit test_service is OPEN"):
            await circuit.call(mock_func)
        
        mock_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_half_open_success_restores_closed(self):
        """Тест восстановления из HALF_OPEN в CLOSED после успешных вызовов"""
        circuit = CircuitBreaker("test_service", CircuitConfig(
            failure_threshold=1,
            recovery_timeout=1,  # 1 секунда для теста
            success_threshold=2
        ))
        
        # Переводим в OPEN
        circuit.state = CircuitState.OPEN
        circuit.last_failure_time = time.time() - 2  # Прошло больше recovery_timeout
        
        mock_func = AsyncMock(return_value="success")
        
        # Первый успешный вызов в HALF_OPEN
        result = await circuit.call(mock_func)
        assert result == "success"
        assert circuit.state == CircuitState.HALF_OPEN
        assert circuit.success_count == 1
        
        # Второй успешный вызов - должно восстановиться в CLOSED
        result = await circuit.call(mock_func)
        assert result == "success"
        assert circuit.state == CircuitState.CLOSED
        assert circuit.success_count == 0  # Должно сброситься после восстановления

    @pytest.mark.asyncio
    async def test_half_open_failure_returns_to_open(self):
        """Тест возврата в OPEN из HALF_OPEN после неудачи"""
        circuit = CircuitBreaker("test_service", CircuitConfig(
            failure_threshold=1,
            recovery_timeout=1
        ))
        
        # Переводим в OPEN
        circuit.state = CircuitState.OPEN
        circuit.last_failure_time = time.time() - 2
        
        mock_func = AsyncMock(side_effect=Exception("Service down"))
        
        # Неудачный вызов в HALF_OPEN - должно вернуться в OPEN
        with pytest.raises(Exception):
            await circuit.call(mock_func)
        
        assert circuit.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_recovery_timeout_respected(self):
        """Тест соблюдения времени восстановления"""
        circuit = CircuitBreaker("test_service", CircuitConfig(
            failure_threshold=1,
            recovery_timeout=1  # 1 секунда
        ))
        
        circuit.state = CircuitState.OPEN
        circuit.last_failure_time = time.time() - 0.5  # Прошло только 0.5 секунды
        
        mock_func = AsyncMock(return_value="success")
        
        # Должно остаться в OPEN, так как не прошло recovery_timeout
        with pytest.raises(Exception, match="Circuit test_service is OPEN"):
            await circuit.call(mock_func)
        
        mock_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_sliding_window_failure_counting(self):
        """Тест подсчета неудач в скользящем окне"""
        circuit = CircuitBreaker("test_service", CircuitConfig(
            failure_threshold=3,
            sliding_window_size=5
        ))
        
        mock_func = AsyncMock(side_effect=Exception("Service down"))
        
        # 2 неудачи
        for _ in range(2):
            with pytest.raises(Exception):
                await circuit.call(mock_func)
        
        assert circuit.state == CircuitState.CLOSED
        assert len(circuit.failure_history) == 2
        
        # Еще 2 неудачи - всего 4, но sliding_window_size=5
        for _ in range(2):
            with pytest.raises(Exception):
                await circuit.call(mock_func)
        
        assert circuit.state == CircuitState.CLOSED
        assert len(circuit.failure_history) == 4
        
        # Еще 2 неудачи - должно перейти в OPEN (6 неудач, но окно = 5)
        for _ in range(2):
            with pytest.raises(Exception):
                await circuit.call(mock_func)
        
        assert circuit.state == CircuitState.OPEN
        assert len(circuit.failure_history) == 5  # Ограничено sliding_window_size

    @pytest.mark.asyncio
    async def test_unexpected_exceptions_not_recorded(self):
        """Тест что неожиданные исключения не записываются как неудачи"""
        circuit = CircuitBreaker("test_service", CircuitConfig(
            failure_threshold=1,
            expected_exception=ConnectionError
        ))
        
        mock_func = AsyncMock(side_effect=ValueError("Unexpected error"))
        
        # ValueError не должен записываться как failure
        with pytest.raises(ValueError):
            await circuit.call(mock_func)
        
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0

    def test_get_state_returns_correct_info(self):
        """Тест получения состояния circuit breaker"""
        circuit = CircuitBreaker("test_service", CircuitConfig())
        circuit.state = CircuitState.OPEN
        circuit.failure_count = 5
        circuit.success_count = 2
        circuit.last_failure_time = time.time()
        
        state = circuit.get_state()
        
        assert state["name"] == "test_service"
        assert state["state"] == "open"
        assert state["failure_count"] == 5
        assert state["success_count"] == 2

    @pytest.mark.asyncio
    async def test_sync_function_execution(self):
        """Тест выполнения синхронных функций"""
        circuit = CircuitBreaker("test_service", CircuitConfig())
        
        def sync_func():
            return "sync_success"
        
        result = await circuit.call(sync_func)
        assert result == "sync_success"
        assert circuit.state == CircuitState.CLOSED


class TestCircuitBreakerManager:
    """Тесты для менеджера Circuit Breaker"""

    def test_create_and_get_circuit(self):
        """Тест создания и получения circuit breaker"""
        manager = CircuitBreakerManager()
        
        circuit = manager.create_circuit("test_service")
        assert circuit is not None
        assert circuit.name == "test_service"
        
        retrieved = manager.get_circuit("test_service")
        assert retrieved == circuit
        
        # Повторное создание возвращает существующий
        same_circuit = manager.create_circuit("test_service")
        assert same_circuit == circuit

    def test_get_nonexistent_circuit(self):
        """Тест получения несуществующего circuit breaker"""
        manager = CircuitBreakerManager()
        circuit = manager.get_circuit("nonexistent")
        assert circuit is None

    def test_get_all_circuits(self):
        """Тест получения всех circuit breakers"""
        manager = CircuitBreakerManager()
        
        circuit1 = manager.create_circuit("service1")
        circuit2 = manager.create_circuit("service2")
        
        all_circuits = manager.get_all_circuits()
        assert len(all_circuits) == 2
        assert "service1" in all_circuits
        assert "service2" in all_circuits

    def test_reset_circuit(self):
        """Тест ручного сброса circuit breaker"""
        manager = CircuitBreakerManager()
        circuit = manager.create_circuit("test_service")
        
        # Переводим в OPEN
        circuit.state = CircuitState.OPEN
        circuit.failure_count = 5
        
        # Сбрасываем
        success = manager.reset_circuit("test_service")
        assert success is True
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0

    def test_reset_nonexistent_circuit(self):
        """Тест сброса несуществующего circuit breaker"""
        manager = CircuitBreakerManager()
        success = manager.reset_circuit("nonexistent")
        assert success is False

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Тест проверки здоровья"""
        manager = CircuitBreakerManager()
        
        circuit1 = manager.create_circuit("service1")
        circuit2 = manager.create_circuit("service2")
        circuit2.state = CircuitState.OPEN
        
        health = await manager.health_check()
        
        assert health["total_circuits"] == 2
        assert health["open_circuits"] == ["service2"]
        assert health["closed_circuits"] == ["service1"]
        assert len(health["details"]) == 2


class TestCircuitConfigs:
    """Тесты предустановленных конфигураций"""

    def test_telegram_api_config(self):
        """Тест конфигурации для Telegram API"""
        config = CircuitConfigs.telegram_api()
        assert config.failure_threshold == 3
        assert config.recovery_timeout == 30

    def test_payment_service_config(self):
        """Тест конфигурации для платежной системы"""
        config = CircuitConfigs.payment_service()
        assert config.failure_threshold == 5
        assert config.recovery_timeout == 120

    def test_fragment_service_config(self):
        """Тест конфигурации для Fragment API"""
        config = CircuitConfigs.fragment_service()
        assert config.failure_threshold == 3
        assert config.recovery_timeout == 60


if __name__ == "__main__":
    pytest.main([__file__])