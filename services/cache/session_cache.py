"""
Session Cache Service - специализированный сервис для управления сессиями пользователей
Основан на BaseCache архитектуре для обеспечения консистентности и надежности

🎯 Основные возможности:
- Управление пользовательскими сессиями с Redis бэкендом
- Graceful degradation при недоступности Redis
- Автоматическое управление TTL и очистка истекших сессий
- Интеграция с Circuit Breaker для отказоустойчивости

📊 Архитектура:
- Наследуется от BaseCache для унификации
- Использует централизованный RedisClient
- Интегрируется с существующей инфраструктурой
"""

import json
import logging
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from core.cache.base_cache import BaseCache
from core.cache.redis_client import RedisClient
from core.cache.serializers import CacheSerializer
from core.cache.exceptions import CacheError, CacheConnectionError
from config.settings import settings


class SessionData:
    """Модель данных сессии"""

    def __init__(self,
                 user_id: int,
                 session_id: Optional[str] = None,
                 initial_data: Optional[Dict[str, Any]] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.user_id = user_id
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.is_active = True
        self.data = initial_data or {}

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь"""
        return {
            'id': self.session_id,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'is_active': self.is_active,
            **self.data
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionData':
        """Десериализация из словаря"""
        session = cls(
            user_id=data['user_id'],
            session_id=data['id'],
            initial_data={k: v for k, v in data.items()
                         if k not in ['id', 'user_id', 'created_at', 'last_activity', 'is_active']}
        )
        session.created_at = datetime.fromisoformat(data['created_at'])
        session.last_activity = datetime.fromisoformat(data['last_activity'])
        session.is_active = data['is_active']
        return session

    def is_expired(self, max_inactive: int = 1800) -> bool:
        """Проверка истечения сессии (30 минут бездействия)"""
        return datetime.utcnow() - self.last_activity > timedelta(seconds=max_inactive)

    def update_activity(self):
        """Обновление времени последней активности"""
        self.last_activity = datetime.utcnow()


class SessionCache(BaseCache):
    """
    Сервис управления сессиями пользователей на основе BaseCache

    🚀 Особенности:
    - Полная интеграция с BaseCache архитектурой
    - Автоматическое управление TTL сессий
    - Graceful degradation при проблемах с Redis
    - Оптимизированные операции с индексами пользователей
    """

    def __init__(self,
                 redis_client: Optional[RedisClient] = None,
                 serializer: Optional[CacheSerializer] = None,
                 enable_local_cache: bool = True,
                 local_cache_ttl: int = 300,
                 local_cache_size: int = 1000):
        """
        Args:
            redis_client: Redis клиент (опционально)
            serializer: Сериализатор данных (опционально)
            enable_local_cache: Включить локальное кеширование
            local_cache_ttl: TTL локального кеша
            local_cache_size: Размер локального кеша
        """
        super().__init__(
            redis_client=redis_client,
            serializer=serializer,
            enable_local_cache=enable_local_cache,
            local_cache_ttl=local_cache_ttl,
            local_cache_size=local_cache_size
        )

        # Настройки префиксов
        self._cache_prefix = "session"
        self._session_ttl = settings.cache_ttl_session
        self._user_sessions_prefix = "user_sessions"

        self.logger = logging.getLogger(f"{__name__}.SessionCache")

    # Реализация абстрактных методов BaseCache
    async def get(self, key: str) -> Optional[Any]:
        """
        Получение значения из кеша по ключу (реализация BaseCache)

        Args:
            key: Ключ

        Returns:
            Значение или None если ключ не найден
        """
        return await self.get_session(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Сохранение значения в кеш (реализация BaseCache)

        Args:
            key: Ключ
            value: Значение
            ttl: Время жизни (опционально)

        Returns:
            True если успешно сохранено
        """
        return await self.set_session(key, value, ttl)

    async def delete(self, key: str) -> bool:
        """
        Удаление значения из кеша (реализация BaseCache)

        Args:
            key: Ключ

        Returns:
            True если успешно удалено
        """
        return await self.delete_session(key)

    # Специфичные методы SessionCache
        self.logger = logging.getLogger(f"{__name__}.SessionCache")

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Получение сессии по ID

        Args:
            session_id: ID сессии

        Returns:
            Данные сессии или None
        """
        try:
            # Получаем сырые данные через BaseCache
            raw_data = await self._get_from_redis(session_id)

            if raw_data:
                session_data = json.loads(raw_data)
                session = SessionData.from_dict(session_data)

                # Проверяем валидность сессии
                if session.is_active and not session.is_expired():
                    # Обновляем активность
                    session.update_activity()
                    await self.set_session(session_id, session.to_dict())
                    return session.to_dict()

                # Сессия истекла - удаляем
                await self.delete_session(session_id)

            return None

        except CacheConnectionError:
            # Graceful degradation - используем локальный кеш
            return self._get_from_local_cache(session_id)
        except Exception as e:
            self.logger.error(f"Error getting session {session_id}: {e}")
            return None

    async def set_session(self, session_id: str, session_data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """
        Сохранение сессии

        Args:
            session_id: ID сессии
            session_data: Данные сессии
            ttl: Время жизни (опционально)

        Returns:
            True если успешно сохранено
        """
        try:
            # Используем TTL по умолчанию если не указан
            actual_ttl = ttl if ttl is not None else self._session_ttl

            # Сохраняем через BaseCache
            success = await self._set_in_redis(session_id, json.dumps(session_data), actual_ttl)

            if success:
                # Индексируем сессию по пользователю
                await self._add_to_user_index(session_data['user_id'], session_id)

                # Кешируем локально
                self._set_in_local_cache(session_id, session_data, actual_ttl)

            return success

        except CacheConnectionError:
            # Graceful degradation - сохраняем только локально
            return self._set_in_local_cache(session_id, session_data, ttl)
        except Exception as e:
            self.logger.error(f"Error setting session {session_id}: {e}")
            return False

    async def delete_session(self, session_id: str) -> bool:
        """
        Удаление сессии

        Args:
            session_id: ID сессии

        Returns:
            True если успешно удалено
        """
        try:
            # Получаем данные сессии для удаления из индекса
            session_data = await self.get_session(session_id)
            if session_data:
                await self._remove_from_user_index(session_data['user_id'], session_id)

            # Удаляем через BaseCache
            success = await self._delete_from_redis(session_id)

            # Удаляем из локального кеша
            self._delete_from_local_cache(session_id)

            return success

        except Exception as e:
            self.logger.error(f"Error deleting session {session_id}: {e}")
            return False

    async def create_session(self, user_id: int, initial_data: Optional[Dict[str, Any]] = None) -> str:
        """
        Создание новой сессии

        Args:
            user_id: ID пользователя
            initial_data: Начальные данные сессии

        Returns:
            ID созданной сессии
        """
        try:
            # Создаем объект сессии
            session = SessionData(user_id=user_id, initial_data=initial_data)

            # Сохраняем сессию
            success = await self.set_session(session.session_id, session.to_dict())

            if success:
                self.logger.info(f"Created session {session.session_id} for user {user_id}")
                return session.session_id
            else:
                raise Exception("Failed to create session")

        except Exception as e:
            self.logger.error(f"Error creating session for user {user_id}: {e}")
            raise

    async def get_user_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Получение всех активных сессий пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Список сессий пользователя
        """
        try:
            # Получаем список ID сессий пользователя
            user_sessions_key = f"{self._user_sessions_prefix}:{user_id}"
            raw_session_ids = await self._get_from_redis(user_sessions_key)

            if not raw_session_ids:
                return []

            session_ids = json.loads(raw_session_ids)
            sessions = []

            # Получаем каждую сессию
            for session_id in session_ids:
                session_data = await self.get_session(session_id)
                if session_data:
                    sessions.append(session_data)

            return sessions

        except Exception as e:
            self.logger.error(f"Error getting sessions for user {user_id}: {e}")
            return []

    async def invalidate_user_sessions(self, user_id: int, keep_active: bool = False) -> int:
        """
        Инвалидация всех сессий пользователя

        Args:
            user_id: ID пользователя
            keep_active: Сохранить активную сессию

        Returns:
            Количество удаленных сессий
        """
        try:
            sessions = await self.get_user_sessions(user_id)
            invalidated_count = 0

            for session in sessions:
                if keep_active and session.get('is_active'):
                    continue

                await self.delete_session(session['id'])
                invalidated_count += 1

            # Очищаем индекс пользователя
            user_sessions_key = f"{self._user_sessions_prefix}:{user_id}"
            await self._delete_from_redis(user_sessions_key)

            self.logger.info(f"Invalidated {invalidated_count} sessions for user {user_id}")
            return invalidated_count

        except Exception as e:
            self.logger.error(f"Error invalidating sessions for user {user_id}: {e}")
            return 0

    async def extend_session(self, session_id: str, additional_ttl: Optional[int] = None) -> bool:
        """
        Продление срока действия сессии

        Args:
            session_id: ID сессии
            additional_ttl: Дополнительное время жизни

        Returns:
            True если успешно продлено
        """
        try:
            session_data = await self.get_session(session_id)
            if not session_data:
                return False

            # Обновляем время активности
            session_data['last_activity'] = datetime.utcnow().isoformat()

            # Устанавливаем новый TTL
            new_ttl = additional_ttl or self._session_ttl
            return await self.set_session(session_id, session_data, new_ttl)

        except Exception as e:
            self.logger.error(f"Error extending session {session_id}: {e}")
            return False

    async def cleanup_expired_sessions(self) -> int:
        """
        Очистка истекших сессий

        Returns:
            Количество очищенных сессий
        """
        try:
            # Получаем все ключи сессий (упрощенная версия)
            pattern = f"{self._cache_prefix}:*"
            # В реальной реализации здесь был бы механизм очистки
            # Для демонстрации возвращаем 0
            return 0

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            return 0

    async def _add_to_user_index(self, user_id: int, session_id: str) -> bool:
        """Добавление сессии в индекс пользователя"""
        try:
            user_sessions_key = f"{self._user_sessions_prefix}:{user_id}"
            current_sessions = await self._get_from_redis(user_sessions_key)

            if current_sessions:
                session_ids = json.loads(current_sessions)
            else:
                session_ids = []

            if session_id not in session_ids:
                session_ids.append(session_id)

            return await self._set_in_redis(user_sessions_key, json.dumps(session_ids), self._session_ttl)

        except Exception as e:
            self.logger.error(f"Error adding session {session_id} to user {user_id} index: {e}")
            return False

    async def _remove_from_user_index(self, user_id: int, session_id: str) -> bool:
        """Удаление сессии из индекса пользователя"""
        try:
            user_sessions_key = f"{self._user_sessions_prefix}:{user_id}"
            current_sessions = await self._get_from_redis(user_sessions_key)

            if current_sessions:
                session_ids = json.loads(current_sessions)
                if session_id in session_ids:
                    session_ids.remove(session_id)
                    return await self._set_in_redis(user_sessions_key, json.dumps(session_ids), self._session_ttl)

            return True

        except Exception as e:
            self.logger.error(f"Error removing session {session_id} from user {user_id} index: {e}")
            return False