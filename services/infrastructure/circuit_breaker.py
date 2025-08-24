"""
Circuit Breaker Service - реализация паттерна Circuit Breaker для устойчивости
"""
import asyncio
import json
import time
from typing import Dict, Any, Optional, Callable, Awaitable
from enum import Enum
from dataclasses import dataclass
import logging


class CircuitState(Enum):
    """Состояния Circuit Breaker"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitConfig:
    """Конфигурация Circuit Breaker"""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    expected_exception: type = Exception
    success_threshold: int = 2
    sliding_window_size: int = 10


class CircuitBreaker:
    """Circuit Breaker для защиты от каскадных сбоев"""

    def __init__(self, name: str, config: CircuitConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.failure_history = []
        self.logger = logging.getLogger(f"circuit_breaker.{name}")

    def _record_failure(self, exception: Exception) -> None:
        """Запись неудачного вызова"""
        current_time = time.time()

        # Безопасно получаем информацию об исключении
        exception_str = str(exception)
        exception_type = type(exception).__name__

        # Проверяем, содержит ли исключение информацию, которая может вызвать ошибку
        try:
            # Пробуем сериализовать исключение
            test_data = {
                "timestamp": current_time,
                "exception": exception_str,
                "type": exception_type
            }
            json.dumps(test_data)  # Пробуем сериализовать
        except (TypeError, ValueError) as json_error:
            self.logger.error(f"Failed to serialize exception data: {json_error}")
            # Используем упрощенные данные
            exception_str = f"Error: {exception_str}"
            exception_type = "Unknown"

        self.failure_history.append({
            "timestamp": current_time,
            "exception": exception_str,
            "type": exception_type
        })

        # Ограничиваем историю
        if len(self.failure_history) > self.config.sliding_window_size:
            self.failure_history.pop(0)

        self.failure_count += 1
        self.last_failure_time = current_time

        self.logger.warning(f"Circuit {self.name} recorded failure: {exception}")
        self.logger.debug(f"Circuit {self.name} failure details - type: {exception_type}, message: {exception_str}")

    def _record_success(self) -> None:
        """Запись успешного вызова"""
        self.success_count += 1

    def _should_trip(self) -> bool:
        """Проверка, должен ли Circuit Breaker перейти в OPEN"""
        if len(self.failure_history) < self.config.failure_threshold:
            return False

        # Проверяем последние N вызовов
        recent_failures = len(self.failure_history[-self.config.failure_threshold:])
        return recent_failures >= self.config.failure_threshold

    def _can_attempt_reset(self) -> bool:
        """Проверка, можно ли попытаться восстановиться"""
        if self.last_failure_time is None:
            return False

        return time.time() - self.last_failure_time >= self.config.recovery_timeout

    def _reset(self) -> None:
        """Сброс Circuit Breaker"""
        self.failure_count = 0
        self.success_count = 0
        self.failure_history.clear()
        self.last_failure_time = None

    def get_state(self) -> Dict[str, Any]:
        """Получение текущего состояния"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "failure_rate": len(self.failure_history) / max(len(self.failure_history), 1),
            "recent_failures": len(self.failure_history[-5:]) if len(self.failure_history) >= 5 else len(self.failure_history)
        }

    async def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Выполнение защищенного вызова с поддержкой синхронных и асинхронных функций"""
        self.logger.info(f"Circuit {self.name} call started with function: {func.__name__}")
        self.logger.info(f"Circuit {self.name} state: {self.state}")

        if self.state == CircuitState.OPEN:
            if self._can_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.logger.info(f"Circuit {self.name} moving to HALF_OPEN state")
            else:
                self.logger.warning(f"Circuit {self.name} is OPEN, raising exception")
                raise Exception(f"Circuit {self.name} is OPEN")

        try:
            # Проверяем, является ли функция корутиной
            import asyncio
            is_async = asyncio.iscoroutinefunction(func)
            self.logger.info(f"Circuit {self.name} function is async: {is_async}")

            if is_async:
                self.logger.info(f"Circuit {self.name} calling async function: {func.__name__}")
                self.logger.info(f"Circuit {self.name} function type: {type(func)}")
                self.logger.info(f"Circuit {self.name} function args: {args}")
                self.logger.info(f"Circuit {self.name} function kwargs: {kwargs}")

                try:
                    result = await func(*args, **kwargs)
                    self.logger.info(f"Circuit {self.name} async function succeeded, result type: {type(result)}, value: {result}")
                except Exception as e:
                    self.logger.error(f"Circuit {self.name} async function failed: {e}")
                    self.logger.error(f"Exception type: {type(e)}")
                    raise
            else:
                self.logger.info(f"Circuit {self.name} calling sync function: {func.__name__}")
                self.logger.info(f"Circuit {self.name} function type: {type(func)}")
                self.logger.info(f"Circuit {self.name} function args: {args}")
                self.logger.info(f"Circuit {self.name} function kwargs: {kwargs}")

                # Для синхронных функций выполняем их в executor
                loop = asyncio.get_event_loop()
                self.logger.info(f"Circuit {self.name} executing sync function in executor")

                # Используем отдельную функцию для выполнения синхронной функции
                def execute_sync_function():
                    try:
                        self.logger.info(f"Executing sync function: {func.__name__}")
                        self.logger.info(f"Function args: {args}")
                        self.logger.info(f"Function kwargs: {kwargs}")

                        result = func(*args, **kwargs)
                        self.logger.info(f"Sync function executed successfully, result: {result} (type: {type(result)})")

                        # Проверяем, не является ли результат bool, который может вызвать проблему
                        if isinstance(result, bool):
                            self.logger.warning(f"Sync function returned boolean result: {result} (type: {type(result)})")

                        return result
                    except Exception as e:
                        self.logger.error(f"Sync function execution failed: {e}")
                        self.logger.error(f"Exception type: {type(e)}")
                        raise

                try:
                    # Выполняем синхронную функцию в executor и ждем результат
                    result = await loop.run_in_executor(None, execute_sync_function)
                    self.logger.info(f"Circuit {self.name} sync function result: {result} (type: {type(result)})")

                    # Проверяем, не является ли результат coroutine (ошибка)
                    if asyncio.iscoroutine(result):
                        self.logger.error(f"Circuit {self.name} ERROR: Sync function returned coroutine instead of result!")
                        # Ждем coroutine чтобы избежать RuntimeWarning
                        try:
                            awaited_result = await result
                            self.logger.warning(f"Circuit {self.name} Coroutine awaited, result: {awaited_result}")
                            result = awaited_result
                        except Exception as await_error:
                            self.logger.error(f"Circuit {self.name} Error awaiting coroutine: {await_error}")
                            raise await_error
                    else:
                        # Результат не является coroutine, это нормально
                        self.logger.info(f"Circuit {self.name} Sync function returned direct result: {result}")

                except Exception as e:
                    self.logger.error(f"Circuit {self.name} sync function execution in executor failed: {e}")
                    self.logger.error(f"Exception type: {type(e)}")
                    raise

            self.logger.info(f"Circuit {self.name} call succeeded")
            self._record_success()

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self._reset()
                    self.logger.info(f"Circuit {self.name} restored to CLOSED state")

            return result

        except Exception as e:
            self.logger.error(f"Circuit {self.name} call failed with exception: {e}")
            self.logger.error(f"Exception type: {type(e)}")
            self.logger.error(f"Exception args: {e.args}")

            # Проверяем тип исключения
            if isinstance(e, self.config.expected_exception):
                self.logger.info(f"Exception is expected type: {self.config.expected_exception}")
                self._record_failure(e)

                if self.state == CircuitState.HALF_OPEN:
                    self.state = CircuitState.OPEN
                    self.logger.warning(f"Circuit {self.name} failed in HALF_OPEN, returning to OPEN")
                elif self._should_trip():
                    self.state = CircuitState.OPEN
                    self.logger.error(f"Circuit {self.name} tripped to OPEN state")

                raise e
            else:
                # Неожиданные исключения не влияют на Circuit Breaker
                self.logger.error(f"Unexpected exception in circuit {self.name}: {e}")
                raise e


class CircuitBreakerManager:
    """Менеджер для управления несколькими Circuit Breakers"""

    def __init__(self):
        self.circuits: Dict[str, CircuitBreaker] = {}
        self.logger = logging.getLogger("circuit_breaker.manager")

    def create_circuit(self, name: str, config: Optional[CircuitConfig] = None) -> CircuitBreaker:
        """Создание нового Circuit Breaker"""
        if name in self.circuits:
            return self.circuits[name]

        config = config or CircuitConfig()
        circuit = CircuitBreaker(name, config)
        self.circuits[name] = circuit

        self.logger.info(f"Created circuit breaker: {name}")
        return circuit

    def get_circuit(self, name: str) -> Optional[CircuitBreaker]:
        """Получение Circuit Breaker по имени"""
        return self.circuits.get(name)

    def get_all_circuits(self) -> Dict[str, Dict[str, Any]]:
        """Получение состояния всех Circuit Breakers"""
        return {name: circuit.get_state() for name, circuit in self.circuits.items()}

    def reset_circuit(self, name: str) -> bool:
        """Ручной сброс Circuit Breaker"""
        circuit = self.circuits.get(name)
        if circuit:
            circuit.state = CircuitState.CLOSED
            circuit._reset()
            self.logger.info(f"Manually reset circuit: {name}")
            return True
        return False

    async def health_check(self) -> Dict[str, Any]:
        """Проверка здоровья всех Circuit Breakers"""
        return {
            "total_circuits": len(self.circuits),
            "open_circuits": [name for name, circuit in self.circuits.items() if circuit.state == CircuitState.OPEN],
            "half_open_circuits": [name for name, circuit in self.circuits.items() if circuit.state == CircuitState.HALF_OPEN],
            "closed_circuits": [name for name, circuit in self.circuits.items() if circuit.state == CircuitState.CLOSED],
            "details": self.get_all_circuits()
        }


# Готовые конфигурации для различных сервисов
class CircuitConfigs:
    """Предустановленные конфигурации для различных сервисов"""

    @staticmethod
    def telegram_api() -> CircuitConfig:
        """Конфигурация для Telegram API"""
        return CircuitConfig(
            failure_threshold=3,
            recovery_timeout=30,
            expected_exception=Exception
        )

    @staticmethod
    def payment_service() -> CircuitConfig:
        """Конфигурация для платежной системы"""
        return CircuitConfig(
            failure_threshold=5,
            recovery_timeout=120,
            expected_exception=Exception
        )

    @staticmethod
    def database() -> CircuitConfig:
        """Конфигурация для базы данных"""
        return CircuitConfig(
            failure_threshold=3,
            recovery_timeout=60,
            expected_exception=Exception
        )

    @staticmethod
    def redis() -> CircuitConfig:
        """Конфигурация для Redis"""
        return CircuitConfig(
            failure_threshold=2,
            recovery_timeout=15,
            expected_exception=Exception
        )


# Глобальный менеджер
circuit_manager = CircuitBreakerManager()
