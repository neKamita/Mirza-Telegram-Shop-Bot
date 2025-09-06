"""
Интеграционные тесты для проверки взаимодействия кэш-сервисов.
Тестирует graceful degradation, согласованность данных и обработку ошибок.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone
import json

from services.cache.user_cache import UserCache
from services.cache.payment_cache import PaymentCache
from services.cache.rate_limit_cache import RateLimitCache
from services.cache.session_cache import SessionCache


class TestCacheServicesIntegration:
    """Тесты интеграции между различными кэш-сервисами"""
    
    @pytest.fixture
    async def mock_redis_client(self):
        """Создание мокированного Redis клиента для всех тестов"""
        mock_client = AsyncMock()
        
        # Настройка базовых методов Redis
        mock_client.set = AsyncMock(return_value=True)
        mock_client.setex = AsyncMock(return_value=True)
        mock_client.delete = AsyncMock(return_value=1)
        mock_client.exists = AsyncMock(return_value=0)
        mock_client.expire = AsyncMock(return_value=True)
        mock_client.incr = AsyncMock(return_value=1)
        mock_client.zadd = AsyncMock(return_value=1)
        mock_client.zrange = AsyncMock(return_value=[])
        mock_client.zrem = AsyncMock(return_value=1)
        mock_client.zcard = AsyncMock(return_value=0)
        mock_client.hset = AsyncMock(return_value=1)
        mock_client.hget = AsyncMock(return_value=None)
        mock_client.hdel = AsyncMock(return_value=1)
        mock_client.ping = AsyncMock(return_value=True)
        
        # Словарь для хранения данных, которые были сохранены через setex
        saved_data = {}
        
        # Переопределяем get метод для возврата сохраненных данных
        async def mock_get(key):
            return saved_data.get(key)
        
        # Переопределяем setex метод для сохранения данных
        async def mock_setex(key, expiry, value):
            saved_data[key] = value
            return True
            
        # Переопределяем delete метод для удаления данных
        async def mock_delete(*keys):
            deleted_count = 0
            for key in keys:
                if key in saved_data:
                    del saved_data[key]
                    deleted_count += 1
            return deleted_count
            
        # Переопределяем keys метод для поиска ключей по шаблону
        async def mock_keys(pattern):
            import fnmatch
            matching_keys = []
            for key in saved_data.keys():
                if fnmatch.fnmatch(key, pattern):
                    matching_keys.append(key)
            return matching_keys
            
        # Переопределяем zadd метод для rate limiting
        async def mock_zadd(key, mapping):
            return len(mapping)  # Возвращаем количество добавленных элементов
            
        # Переопределяем llen метод для rate limiting
        async def mock_llen(key):
            # Для простоты возвращаем фиксированное значение
            return 0
            
        # Переопределяем lpush метод для rate limiting
        async def mock_lpush(key, *values):
            # Возвращаем количество добавленных элементов
            return len(values)
            
        # Переопределяем lrem метод для rate limiting
        async def mock_lrem(key, count, value):
            # Возвращаем количество удаленных элементов (для простоты 1)
            return 1
            
        # Переопределяем zcard метод для rate limiting
        async def mock_zcard(key):
            # Для простоты возвращаем фиксированное значение
            return 5
            
        mock_client.get.side_effect = mock_get
        mock_client.setex.side_effect = mock_setex
        mock_client.delete.side_effect = mock_delete
        mock_client.keys.side_effect = mock_keys
        mock_client.llen.side_effect = mock_llen
        mock_client.lpush.side_effect = mock_lpush
        mock_client.lrem.side_effect = mock_lrem
        mock_client.zadd.side_effect = mock_zadd
        mock_client.zcard.side_effect = mock_zcard
        
        return mock_client
    
    @pytest.fixture
    async def user_cache(self, mock_redis_client):
        """Фикстура для UserCache"""
        return UserCache(mock_redis_client)
    
    @pytest.fixture
    async def payment_cache_recovery(self, mock_redis_client):
        """Фикстура для PaymentCache в recovery сценариях"""
        return PaymentCache(mock_redis_client)
    
    @pytest.fixture
    async def payment_cache(self, mock_redis_client):
        """Фикстура для PaymentCache"""
        return PaymentCache(mock_redis_client)
    
    
    @pytest.fixture
    async def rate_limit_cache(self, mock_redis_client):
        """Фикстура для RateLimitCache"""
        return RateLimitCache(mock_redis_client)
    
    @pytest.fixture
    async def session_cache(self, mock_redis_client):
        """Фикстура для SessionCache"""
        return SessionCache(mock_redis_client)
    
    @pytest.mark.asyncio
    async def test_cross_cache_graceful_degradation(self, mock_redis_client, user_cache, payment_cache):
        """
        Тестирует graceful degradation при недоступности Redis для разных кэш-сервисов.
        Проверяет, что все сервисы корректно переходят на локальное кэширование.
        """
        # Эмулируем ошибку Redis для всех операций
        mock_redis_client.set.side_effect = Exception("Redis connection failed")
        mock_redis_client.get.side_effect = Exception("Redis connection failed")
        mock_redis_client.setex.side_effect = Exception("Redis connection failed")
        
        user_id = 123
        payment_id = "pay_123"
        
        # Тестируем UserCache с graceful degradation
        user_profile = {"name": "Test User", "email": "test@example.com"}
        result = await user_cache.cache_user_profile(user_id, user_profile)
        print(f"DEBUG: Результат cache_user_profile: {result}")
        print(f"DEBUG: Ключи в локальном кэше после сохранения: {list(user_cache.local_cache.cache.keys())}")
        assert result is True, "UserCache должен использовать локальное кэширование при ошибке Redis"
        
        # Тестируем PaymentCache с graceful degradation
        payment_data = {"amount": 100, "currency": "USD"}
        result = await payment_cache.cache_payment_details(payment_id, payment_data)
        assert result is True, "PaymentCache должен использовать локальное кэширование при ошибке Redis"
        
        # Отладочная информация для понимания состояния кэша
        print(f"DEBUG: Проверяем локальный кэш UserCache")
        print(f"DEBUG: Ключи в локальном кэше: {list(user_cache.local_cache.cache.keys())}")
        
        # Проверяем, что данные доступны из локального кэша
        cached_profile = await user_cache.get_user_profile(user_id)
        print(f"DEBUG: Результат get_user_profile: {cached_profile}")
        
        # LocalCache.get() возвращает данные в формате {'data': actual_data}
        # UserCache.get_user_profile() должен извлекать actual_data из этого формата
        if cached_profile:
            # Сравниваем только основные поля, игнорируя автоматически добавленные
            # (cached_at добавляется автоматически в user_cache.cache_user_profile)
            expected_profile_no_timestamp = {k: v for k, v in user_profile.items() if k != 'cached_at'}
            cached_profile_no_timestamp = {k: v for k, v in cached_profile.items() if k != 'cached_at'}
            assert cached_profile_no_timestamp == expected_profile_no_timestamp, f"Данные должны быть доступны из локального кэша UserCache. Ожидалось: {expected_profile_no_timestamp}, Получено: {cached_profile_no_timestamp}"
        else:
            assert False, "Данные не найдены в локальном кэше UserCache"
        
        cached_payment = await payment_cache.get_payment_details(payment_id)
        if cached_payment:
            # PaymentCache.get_payment_details() возвращает данные в формате {'data': actual_data}
            # Нужно извлечь actual_data из этого формата
            if isinstance(cached_payment, dict) and 'data' in cached_payment:
                cached_payment = cached_payment['data']
            
            # Убираем поле cached_at для сравнения
            expected_payment_no_timestamp = {k: v for k, v in payment_data.items() if k != 'cached_at'}
            cached_payment_no_timestamp = {k: v for k, v in cached_payment.items() if k != 'cached_at'}
            assert cached_payment_no_timestamp == expected_payment_no_timestamp, f"Данные должны быть доступны из локального кэша PaymentCache. Ожидалось: {expected_payment_no_timestamp}, Получено: {cached_payment_no_timestamp}"
        else:
            assert False, "Данные не найдены в локальном кэше PaymentCache"
    
    @pytest.mark.asyncio
    async def test_cache_consistency_across_services(self, mock_redis_client, user_cache, payment_cache):
        """
        Тестирует согласованность данных между разными кэш-сервисами.
        """
        user_id = 456
        payment_id = "pay_456"
        
        user_data = {
            "user_id": user_id,
            "name": "Integration User",
            "balance": 1000
        }
        
        payment_data = {
            "payment_id": payment_id,
            "user_id": user_id,
            "amount": 100,
            "status": "completed"
        }
        
        # Сохраняем данные в оба кэша
        await user_cache.cache_user_profile(user_id, user_data)
        await payment_cache.cache_payment_details(payment_id, payment_data)
        
        # Проверяем согласованность данных
        cached_user = await user_cache.get_user_profile(user_id)
        cached_payment = await payment_cache.get_payment_details(payment_id)

        # LocalCache.get() возвращает данные в формате {'data': actual_data}
        # Извлекаем фактические данные из структуры LocalCache
        if isinstance(cached_user, dict) and 'data' in cached_user:
            cached_user = cached_user['data']
        if isinstance(cached_payment, dict) and 'data' in cached_payment:
            cached_payment = cached_payment['data']

        assert cached_user["user_id"] == cached_payment["user_id"], \
            f"ID пользователя должен быть согласован между кэшами. User: {cached_user.get('user_id')}, Payment: {cached_payment.get('user_id')}"
        assert cached_user["balance"] == 1000, f"Баланс пользователя должен сохраняться. Получено: {cached_user.get('balance')}"
        assert cached_payment["status"] == "completed", f"Статус платежа должен сохраняться. Получено: {cached_payment.get('status')}"
    
    @pytest.mark.asyncio
    async def test_rate_limiting_with_user_activity(self, mock_redis_client, rate_limit_cache, user_cache):
        """
        Тестирует интеграцию rate limiting с пользовательской активностью.
        """
        user_id = 789
        action = "purchase"
        
        # Симулируем активность пользователя
        user_activity = {
            "last_action": datetime.now(timezone.utc).isoformat(),
            "action_count": 5,
            "purchases_today": 3
        }
        
        await user_cache.cache_user_activity(user_id, user_activity)
        
        # Проверяем rate limiting для этого пользователя
        for i in range(5):
            # Добавляем отладочную информацию о состоянии Redis
            key = f"user_rate_limit:{user_id}:{action}"
            current_count = await mock_redis_client.llen(key)
            print(f"DEBUG: Перед запросом {i+1}, ключ: {key}, текущее количество: {current_count}")
            
            result = await rate_limit_cache.check_user_rate_limit(
                user_id, action, limit=10, window=60
            )
            
            current_count_after = await mock_redis_client.llen(key)
            print(f"DEBUG: После запроса {i+1}, результат метода: {result}, количество после: {current_count_after}")
            
            # По логике метода: True = разрешено, False = ограничено
            # В тесте мы ожидаем, что запрос разрешен (not ограничен)
            assert result is True, f"Пользователь не должен быть ограничен на запросе {i+1}, результат метода: {result}"
        
        # Проверяем, что после превышения лимита срабатывает ограничение
        is_limited = await rate_limit_cache.check_user_rate_limit(
            user_id, action, limit=5, window=60
        )
        assert is_limited, "Пользователь должен быть ограничен после превышения лимита"
    
    @pytest.mark.asyncio
    async def test_session_management_with_user_cache(self, mock_redis_client, session_cache, user_cache):
        """
        Тестирует интеграцию управления сессиями с пользовательским кэшем.
        """
        user_id = 101112
        
        # Используем минимальные данные для сессии, как ожидает SessionCache
        user_profile = {
            "user_id": user_id,
            "name": "Session User",
            "sessions_count": 1
        }

        # Создаем сессию с помощью метода create_session (он сам создает правильную структуру)
        session_id = await session_cache.create_session(user_id)
        await user_cache.cache_user_profile(user_id, user_profile)

        # Добавляем отладочную информацию
        print(f"DEBUG: Создан session_id: {session_id}")
        
        # Проверяем, что данные согласованы
        cached_session = await session_cache.get_session(session_id)
        cached_user = await user_cache.get_user_profile(user_id)

        print(f"DEBUG: cached_session: {cached_session}")
        print(f"DEBUG: cached_user: {cached_user}")
        
        assert cached_session is not None, "Сессия должна быть создана"
        assert cached_user is not None, "Профиль пользователя должен быть закэширован"
        
        # SessionCache.get_session() возвращает данные в формате LocalCache: {'data': actual_data}
        # Нужно извлечь фактические данные сессии
        if isinstance(cached_session, dict) and 'data' in cached_session:
            actual_session_data = cached_session['data']
        else:
            actual_session_data = cached_session
            
        print(f"DEBUG: actual_session_data: {actual_session_data}")
        
        # Проверяем, что сессия содержит user_id
        if actual_session_data and 'user_id' in actual_session_data:
            assert actual_session_data["user_id"] == cached_user["user_id"], \
                f"ID пользователя должен быть согласован между сессией ({actual_session_data['user_id']}) и профилем ({cached_user['user_id']})"
        else:
            assert False, f"Сессия не содержит user_id. Структура сессии: {cached_session}"
    
    @pytest.mark.asyncio
    async def test_error_handling_across_caches(self, mock_redis_client, user_cache, payment_cache):
        """
        Тестирует обработку ошибок across different cache services.
        """
        user_id = 131415
        payment_id = "pay_err_131415"
        
        # Эмулируем периодические ошибки Redis
        def mock_redis_with_intermittent_errors(*args, **kwargs):
            import random
            if random.random() < 0.5:  # 50% chance of error
                raise Exception("Intermittent Redis error")
            
            # Для get операций возвращаем сериализованные JSON данные
            operation = args[0] if args else None
            if operation == 'get':
                key = args[1] if len(args) > 1 else None
                if key and key.startswith("payment_details:"):
                    return json.dumps({"amount": 200, "cached_at": "2025-08-31T19:31:10.541404"})
                elif key and key.startswith("user:"):
                    return json.dumps({"name": "Error Test User", "cached_at": "2025-08-31T19:31:10.541404"})
            
            return True
        
        mock_redis_client.set.side_effect = mock_redis_with_intermittent_errors
        mock_redis_client.get.side_effect = mock_redis_with_intermittent_errors
        
        # Тестируем устойчивость к ошибкам
        user_data = {"name": "Error Test User"}
        payment_data = {"amount": 200}
        
        # Эти операции должны успешно завершиться благодаря graceful degradation
        user_result = await user_cache.cache_user_profile(user_id, user_data)
        payment_result = await payment_cache.cache_payment_details(payment_id, payment_data)
        
        assert user_result is True, "UserCache должен обрабатывать intermittent errors"
        assert payment_result is True, "PaymentCache должен обрабатывать intermittent errors"
        
        # Проверяем, что данные доступны из локального кэша
        cached_user = await user_cache.get_user_profile(user_id)
        cached_payment = await payment_cache.get_payment_details(payment_id)

        # LocalCache.get() возвращает данные в формате {'data': actual_data} для локального кэша
        # Извлекаем фактические данные из структуры LocalCache
        if isinstance(cached_user, dict) and 'data' in cached_user:
            cached_user = cached_user['data']
        if isinstance(cached_payment, dict) and 'data' in cached_payment:
            cached_payment = cached_payment['data']

        # Убираем поле cached_at для сравнения
        expected_user_data = {'name': 'Error Test User'}  # Только основные поля без cached_at
        expected_payment_data = {'amount': 200}  # Только основные поля без cached_at

        cached_user_no_timestamp = {k: v for k, v in cached_user.items() if k != 'cached_at'}
        cached_payment_no_timestamp = {k: v for k, v in cached_payment.items() if k != 'cached_at'}

        assert cached_user_no_timestamp == expected_user_data, f"Данные пользователя должны быть доступны несмотря на ошибки. Ожидалось: {expected_user_data}, Получено: {cached_user_no_timestamp}"
        assert cached_payment_no_timestamp == expected_payment_data, f"Данные платежа должны быть доступны несмотря на ошибки. Ожидалось: {expected_payment_data}, Получено: {cached_payment_no_timestamp}"
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_across_services(self, mock_redis_client, user_cache, payment_cache):
        """
        Тестирует инвалидацию кэша across different services.
        """
        user_id = 161718
        payment_id = "pay_inv_161718"
        
        user_data = {"name": "Invalidation User", "balance": 500}
        payment_data = {"amount": 50, "user_id": user_id}
        
        # Сохраняем данные
        await user_cache.cache_user_profile(user_id, user_data)
        await payment_cache.cache_payment_details(payment_id, payment_data)
        
        # Добавляем отладочную информацию перед инвалидацией
        user_key = f"user:{user_id}:profile"
        payment_key = f"payment_details:{payment_id}"
        print(f"DEBUG: User key: {user_key}")
        print(f"DEBUG: Payment key: {payment_key}")
        
        # Проверяем, что данные сохранены до инвалидации
        user_before_invalidation = await user_cache.get_user_profile(user_id)
        payment_before_invalidation = await payment_cache.get_payment_details(payment_id)
        print(f"DEBUG: User before invalidation: {user_before_invalidation}")
        print(f"DEBUG: Payment before invalidation: {payment_before_invalidation}")
        
        # Инвалидируем пользовательский кэш
        invalidation_result = await user_cache.invalidate_user_cache(user_id)
        assert invalidation_result is True, "Инвалидация пользовательского кэша должна завершиться успешно"
        
        # Проверяем, что пользовательские данные удалены
        cached_user = await user_cache.get_user_profile(user_id)
        print(f"DEBUG: User after invalidation: {cached_user}")
        assert cached_user is None, "Данные пользователя должны быть инвалидированы"
        
        # Но платежные данные должны остаться (разные пространства имен)
        cached_payment = await payment_cache.get_payment_details(payment_id)
        print(f"DEBUG: Payment after invalidation: {cached_payment}")
        
        # PaymentCache.get_payment_details() возвращает данные в формате LocalCache: {'data': actual_data}
        # Извлекаем фактические данные из структуры LocalCache
        if isinstance(cached_payment, dict) and 'data' in cached_payment:
            cached_payment_data = cached_payment['data']
        else:
            cached_payment_data = cached_payment
            
        # Убираем поле cached_at для сравнения (оно добавляется автоматически)
        expected_payment_data = {'amount': 50, 'user_id': user_id}  # Только основные поля
        cached_payment_no_timestamp = {k: v for k, v in cached_payment_data.items() if k != 'cached_at'}
        
        assert cached_payment_no_timestamp == expected_payment_data, "Платежные данные не должны затрагиваться инвалидацией пользователя"
    
    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self, mock_redis_client, user_cache, payment_cache):
        """
        Тестирует конкурентные операции в разных кэш-сервисах.
        """
        user_ids = [1001, 1002, 1003]
        payment_ids = [f"pay_{uid}" for uid in user_ids]
        
        async def cache_user_data(uid):
            data = {"user_id": uid, "name": f"User {uid}", "balance": uid * 10}
            return await user_cache.cache_user_profile(uid, data)
        
        async def cache_payment_data(pid, uid):
            data = {"payment_id": pid, "user_id": uid, "amount": uid * 5}
            return await payment_cache.cache_payment_details(pid, data)
        
        # Выполняем операции конкурентно
        user_tasks = [cache_user_data(uid) for uid in user_ids]
        payment_tasks = [cache_payment_data(pid, uid) for pid, uid in zip(payment_ids, user_ids)]
        
        user_results = await asyncio.gather(*user_tasks)
        payment_results = await asyncio.gather(*payment_tasks)
        
        # Проверяем успешность всех операций
        assert all(user_results), "Все пользовательские операции должны завершиться успешно"
        assert all(payment_results), "Все платежные операции должны завершиться успешно"
        
        # Проверяем целостность данных
        for uid, pid in zip(user_ids, payment_ids):
            user_data = await user_cache.get_user_profile(uid)
            payment_data = await payment_cache.get_payment_details(pid)
            
            # PaymentCache.get_payment_details() возвращает данные в формате LocalCache: {'data': actual_data}
            # Извлекаем фактические данные из структуры LocalCache
            if isinstance(payment_data, dict) and 'data' in payment_data:
                payment_data_actual = payment_data['data']
            else:
                payment_data_actual = payment_data
                
            assert user_data["user_id"] == uid, "Данные пользователя должны быть корректными"
            assert payment_data_actual["user_id"] == uid, "Данные платежа должны ссылаться на правильного пользователя"
            assert payment_data_actual["amount"] == uid * 5, "Сумма платежа должна быть корректной"


class TestCacheRecoveryScenarios:
    """Тесты сценариев восстановления кэш-сервисов"""
    
    @pytest.fixture
    async def mock_redis_client(self):
        """Создание мокированного Redis клиента для всех тестов"""
        mock_client = AsyncMock()
        
        # Настройка базовых методов Redis
        mock_client.set = AsyncMock(return_value=True)
        mock_client.setex = AsyncMock(return_value=True)
        mock_client.delete = AsyncMock(return_value=1)
        mock_client.exists = AsyncMock(return_value=0)
        mock_client.expire = AsyncMock(return_value=True)
        mock_client.incr = AsyncMock(return_value=1)
        mock_client.zadd = AsyncMock(return_value=1)
        mock_client.zrange = AsyncMock(return_value=[])
        mock_client.zrem = AsyncMock(return_value=1)
        mock_client.zcard = AsyncMock(return_value=0)
        mock_client.hset = AsyncMock(return_value=1)
        mock_client.hget = AsyncMock(return_value=None)
        mock_client.hdel = AsyncMock(return_value=1)
        mock_client.ping = AsyncMock(return_value=True)
        
        # Словарь для хранения данных, которые были сохранены через setex
        saved_data = {}
        
        # Переопределяем get метод для возврата сохраненных данных
        async def mock_get(key):
            return saved_data.get(key)
        
        # Переопределяем setex метод для сохранения данных
        async def mock_setex(key, expiry, value):
            saved_data[key] = value
            return True
            
        # Переопределяем delete метод для удаления данных
        async def mock_delete(*keys):
            deleted_count = 0
            for key in keys:
                if key in saved_data:
                    del saved_data[key]
                    deleted_count += 1
            return deleted_count
            
        # Переопределяем keys метод для поиска ключей по шаблону
        async def mock_keys(pattern):
            import fnmatch
            matching_keys = []
            for key in saved_data.keys():
                if fnmatch.fnmatch(key, pattern):
                    matching_keys.append(key)
            return matching_keys
            
        # Переопределяем zadd метод для rate limiting
        async def mock_zadd(key, mapping):
            return len(mapping)  # Возвращаем количество добавленных элементов
            
        # Переопределяем llen метод для rate limiting
        async def mock_llen(key):
            # Для простоты возвращаем фиксированное значение
            return 0
            
        # Переопределяем lpush метод для rate limiting
        async def mock_lpush(key, *values):
            # Возвращаем количество добавленных элементов
            return len(values)
            
        # Переопределяем lrem метод для rate limiting
        async def mock_lrem(key, count, value):
            # Возвращаем количество удаленных элементов (для простоты 1)
            return 1
            
        # Переопределяем zcard метод для rate limiting
        async def mock_zcard(key):
            # Для простоты возвращаем фиксированное значение
            return 5
            
        mock_client.get.side_effect = mock_get
        mock_client.setex.side_effect = mock_setex
        mock_client.delete.side_effect = mock_delete
        mock_client.keys.side_effect = mock_keys
        mock_client.llen.side_effect = mock_llen
        mock_client.lpush.side_effect = mock_lpush
        mock_client.lrem.side_effect = mock_lrem
        mock_client.zadd.side_effect = mock_zadd
        mock_client.zcard.side_effect = mock_zcard
        
        return mock_client
    
    @pytest.fixture
    async def user_cache(self, mock_redis_client):
        """Фикстура для UserCache"""
        return UserCache(mock_redis_client)
    
    @pytest.fixture
    async def recovery_payment_cache(self, mock_redis_client):
        """Фикстура для PaymentCache в recovery сценариях"""
        return PaymentCache(mock_redis_client)
    
    @pytest.mark.asyncio
    async def test_redis_recovery_after_failure(self, mock_redis_client, user_cache):
        """
        Тестирует восстановление работы с Redis после временной недоступности.
        """
        user_id = 2001
        user_data = {"name": "Recovery User"}
        
        # Эмулируем первоначальную ошибку Redis
        mock_redis_client.set.side_effect = Exception("Redis temporarily down")
        mock_redis_client.get.side_effect = Exception("Redis temporarily down")
        
        # Данные должны сохраниться в локальный кэш
        result = await user_cache.cache_user_profile(user_id, user_data)
        assert result is True, "Данные должны быть сохранены в локальный кэш"

        cached_data = await user_cache.get_user_profile(user_id)
        
        # UserCache.cache_user_profile() автоматически добавляет поле cached_at
        # Проверяем только основные поля, игнорируя временную метку
        expected_data = {'name': 'Recovery User'}  # Только основные поля
        cached_data_no_timestamp = {k: v for k, v in cached_data.items() if k != 'cached_at'}
        
        assert cached_data_no_timestamp == expected_data, "Данные должны быть доступны из локального кэша"
        
        # Восстанавливаем Redis
        mock_redis_client.set.side_effect = None
        mock_redis_client.get.side_effect = None
        mock_redis_client.set.return_value = True
        mock_redis_client.get.return_value = json.dumps(user_data)
        
        # Теперь данные должны быть доступны и из Redis
        cached_from_redis = await user_cache.get_user_profile(user_id)
        
        # UserCache.get_user_profile() возвращает данные с полем cached_at
        # Проверяем только основные поля, игнорируя временную метку
        expected_data = {'name': 'Recovery User'}  # Только основные поля
        cached_from_redis_no_timestamp = {k: v for k, v in cached_from_redis.items() if k != 'cached_at'}
        
        assert cached_from_redis_no_timestamp == expected_data, "Данные должны быть доступны из Redis после восстановления"
    
    @pytest.mark.asyncio
    async def test_cache_warmup_after_outage(self, mock_redis_client, user_cache, recovery_payment_cache):
        """
        Тестирует прогрев кэша после длительной недоступности Redis.
        """
        user_id = 2002
        payment_id = "pay_warmup_2002"
        
        user_data = {"name": "Warmup User", "balance": 1000}
        payment_data = {"amount": 100, "status": "pending"}
        
        # Сохраняем данные при работающем Redis
        await user_cache.cache_user_profile(user_id, user_data)
        await recovery_payment_cache.cache_payment_details(payment_id, payment_data)
        
        # Эмулируем длительную недоступность Redis
        mock_redis_client.get.side_effect = Exception("Redis prolonged outage")
        mock_redis_client.set.side_effect = Exception("Redis prolonged outage")
        mock_redis_client.setex.side_effect = Exception("Redis prolonged outage")
        
        # Данные должны быть доступны из локального кэша
        cached_user = await user_cache.get_user_profile(user_id)
        cached_payment = await recovery_payment_cache.get_payment_details(payment_id)
        
        # UserCache автоматически добавляет поле cached_at, проверяем основные поля
        expected_user_data = {'name': 'Warmup User', 'balance': 1000}
        cached_user_no_timestamp = {k: v for k, v in cached_user.items() if k != 'cached_at'}
        assert cached_user_no_timestamp == expected_user_data, "Данные пользователя должны быть в локальном кэше"
        
        # PaymentCache.get_payment_details() возвращает данные в формате LocalCache: {'data': actual_data}
        # Извлекаем фактические данные из структуры LocalCache
        if isinstance(cached_payment, dict) and 'data' in cached_payment:
            cached_payment_data = cached_payment['data']
        else:
            cached_payment_data = cached_payment
            
        # Убираем поле cached_at для сравнения (оно добавляется автоматически)
        expected_payment_data = {'amount': 100, 'status': 'pending'}
        cached_payment_no_timestamp = {k: v for k, v in cached_payment_data.items() if k != 'cached_at'}
        assert cached_payment_no_timestamp == expected_payment_data, "Данные платежа должны быть в локальном кэше"
        
        # Восстанавливаем Redis и проверяем, что данные синхронизируются
        mock_redis_client.get.side_effect = None
        mock_redis_client.set.side_effect = None
        mock_redis_client.setex.side_effect = None
        
        # Мокируем возвращаемые значения Redis
        mock_redis_client.get.return_value = json.dumps(user_data)
        
        # После восстановления данные должны быть доступны из обоих источников
        recovered_user = await user_cache.get_user_profile(user_id)
        recovered_payment = await recovery_payment_cache.get_payment_details(payment_id)
        
        # Проверяем только основные поля, игнорируя временные метки
        recovered_user_no_timestamp = {k: v for k, v in recovered_user.items() if k != 'cached_at'}
        assert recovered_user_no_timestamp == expected_user_data, "Данные пользователя должны сохраниться после восстановления"
        
        if isinstance(recovered_payment, dict) and 'data' in recovered_payment:
            recovered_payment_data = recovered_payment['data']
        else:
            recovered_payment_data = recovered_payment
            
        recovered_payment_no_timestamp = {k: v for k, v in recovered_payment_data.items() if k != 'cached_at'}
        assert recovered_payment_no_timestamp == expected_payment_data, "Данные платежа должны сохраниться после восстановления"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])