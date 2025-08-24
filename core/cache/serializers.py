"""
Унифицированные сериализаторы для системы кеширования

Предоставляет безопасную сериализацию/десериализацию данных
с валидацией и обработкой ошибок.
"""

import json
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Dict, Optional, Union
from .exceptions import CacheSerializationError


logger = logging.getLogger(__name__)


class CacheSerializer:
    """
    Сериализатор для кеширования с поддержкой различных типов данных

    Features:
    - Безопасная JSON сериализация с кастомными энкодерами
    - Валидация данных перед сериализацией
    - Обработка специальных типов (datetime, Decimal и т.д.)
    - Контроль размера сериализованных данных
    """

    def __init__(self,
                 max_size: int = 1024 * 1024,  # 1MB
                 validate_data: bool = True,
                 compression_enabled: bool = False):
        """
        Args:
            max_size: Максимальный размер сериализованных данных в байтах
            validate_data: Включить валидацию данных перед сериализацией
            compression_enabled: Включить сжатие данных (резерв для будущих версий)
        """
        self.max_size = max_size
        self.validate_data = validate_data
        self.compression_enabled = compression_enabled

    def serialize(self, data: Any, validate: Optional[bool] = None) -> str:
        """
        Сериализация данных в JSON строку

        Args:
            data: Данные для сериализации
            validate: Переопределить настройку валидации для этого вызова

        Returns:
            JSON строка

        Raises:
            CacheSerializationError: При ошибке сериализации
        """
        try:
            # Валидация данных
            if (validate is True) or (validate is None and self.validate_data):
                self._validate_data(data)

            # Сериализация с кастомными энкодерами
            serialized = json.dumps(data, default=self._default_serializer, ensure_ascii=False)

            # Проверка размера
            if len(serialized.encode('utf-8')) > self.max_size:
                raise CacheSerializationError(
                    f"Serialized data size {len(serialized)} exceeds maximum {self.max_size} bytes",
                    data=data,
                    operation="serialize"
                )

            return serialized

        except Exception as e:
            logger.error(f"Serialization error: {e}")
            raise CacheSerializationError(
                f"Failed to serialize data: {e}",
                data=data,
                operation="serialize"
            ) from e

    def deserialize(self, serialized_data: str, validate: Optional[bool] = None) -> Any:
        """
        Десериализация JSON строки в Python объекты

        Args:
            serialized_data: JSON строка
            validate: Переопределить настройку валидации для этого вызова

        Returns:
            Десериализованные данные

        Raises:
            CacheSerializationError: При ошибке десериализации
        """
        try:
            if not isinstance(serialized_data, str):
                raise CacheSerializationError(
                    "Serialized data must be a string",
                    data=serialized_data,
                    operation="deserialize"
                )

            # Десериализация
            data = json.loads(serialized_data, object_hook=self._object_hook)

            # Валидация данных
            if (validate is True) or (validate is None and self.validate_data):
                self._validate_data(data)

            return data

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            raise CacheSerializationError(
                f"Failed to deserialize JSON data: {e}",
                data=serialized_data,
                operation="deserialize"
            ) from e
        except Exception as e:
            logger.error(f"Deserialization error: {e}")
            raise CacheSerializationError(
                f"Failed to deserialize data: {e}",
                data=serialized_data,
                operation="deserialize"
            ) from e

    def _default_serializer(self, obj: Any) -> Any:
        """
        Кастомный сериализатор для нестандартных типов данных

        Args:
            obj: Объект для сериализации

        Returns:
            Сериализуемое представление объекта
        """
        if isinstance(obj, datetime):
            return {
                "__datetime__": True,
                "value": obj.isoformat()
            }
        elif isinstance(obj, date):
            return {
                "__date__": True,
                "value": obj.isoformat()
            }
        elif isinstance(obj, Decimal):
            return {
                "__decimal__": True,
                "value": str(obj)
            }
        elif isinstance(obj, set):
            return {
                "__set__": True,
                "value": list(obj)
            }
        elif hasattr(obj, '__dict__'):
            # Для объектов с __dict__ (кастомные классы)
            return {
                "__object__": True,
                "class": obj.__class__.__name__,
                "data": obj.__dict__
            }
        else:
            # Попытка сериализовать через str()
            return str(obj)

    def _object_hook(self, obj: Dict[str, Any]) -> Any:
        """
        Кастомный десериализатор для восстановления специальных типов

        Args:
            obj: Объект из JSON

        Returns:
            Восстановленный Python объект
        """
        if "__datetime__" in obj:
            return datetime.fromisoformat(obj["value"])
        elif "__date__" in obj:
            return date.fromisoformat(obj["value"])
        elif "__decimal__" in obj:
            return Decimal(obj["value"])
        elif "__set__" in obj:
            return set(obj["value"])
        elif "__object__" in obj:
            # Для кастомных объектов - возвращаем dict с информацией
            return {
                "__restored_object__": True,
                "class": obj["class"],
                "data": obj["data"]
            }
        else:
            return obj

    def _validate_data(self, data: Any, max_depth: int = 10) -> None:
        """
        Валидация данных перед сериализацией

        Args:
            data: Данные для валидации
            max_depth: Максимальная глубина вложенности

        Raises:
            CacheSerializationError: При обнаружении проблем с данными
        """
        try:
            self._validate_recursive(data, max_depth, current_depth=0)
        except RecursionError:
            raise CacheSerializationError(
                f"Data structure is too deep (max depth: {max_depth})",
                data=data,
                operation="validate"
            )

    def _validate_recursive(self, data: Any, max_depth: int, current_depth: int) -> None:
        """
        Рекурсивная валидация данных

        Args:
            data: Данные для валидации
            max_depth: Максимальная глубина
            current_depth: Текущая глубина

        Raises:
            CacheSerializationError: При обнаружении проблем
        """
        if current_depth > max_depth:
            raise CacheSerializationError(
                f"Data structure depth {current_depth} exceeds maximum {max_depth}",
                data=data,
                operation="validate"
            )

        if isinstance(data, dict):
            for key, value in data.items():
                if not isinstance(key, (str, int, float, bool)) and key is not None:
                    raise CacheSerializationError(
                        f"Invalid dictionary key type: {type(key)}",
                        data=data,
                        operation="validate"
                    )
                self._validate_recursive(value, max_depth, current_depth + 1)

        elif isinstance(data, (list, tuple, set)):
            for item in data:
                self._validate_recursive(item, max_depth, current_depth + 1)

        elif data is not None and not isinstance(data, (str, int, float, bool, type(None))):
            # Проверяем, что объект можно сериализовать
            try:
                self._default_serializer(data)
            except Exception as e:
                raise CacheSerializationError(
                    f"Object of type {type(data)} cannot be serialized: {e}",
                    data=data,
                    operation="validate"
                ) from e


# Глобальный экземпляр сериализатора для использования по умолчанию
default_serializer = CacheSerializer()


def serialize(data: Any, **kwargs) -> str:
    """
    Удобная функция для сериализации данных

    Args:
        data: Данные для сериализации
        **kwargs: Дополнительные параметры для CacheSerializer

    Returns:
        JSON строка
    """
    serializer = CacheSerializer(**kwargs) if kwargs else default_serializer
    return serializer.serialize(data)


def deserialize(serialized_data: str, **kwargs) -> Any:
    """
    Удобная функция для десериализации данных

    Args:
        serialized_data: JSON строка
        **kwargs: Дополнительные параметры для CacheSerializer

    Returns:
        Десериализованные данные
    """
    serializer = CacheSerializer(**kwargs) if kwargs else default_serializer
    return serializer.deserialize(serialized_data)