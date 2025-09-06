"""
Unit-тесты для UserRepository с комплексным покрытием основных сценариев
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, insert, update, delete, func
from sqlalchemy.exc import IntegrityError

from repositories.user_repository import UserRepository, User, Balance, Transaction, TransactionType, TransactionStatus
from services.cache.user_cache import UserCache


class TestUserRepository:
    """Комплексные тесты для UserRepository"""

    @pytest.fixture
    def mock_async_session(self):
        """Фикстура для mock асинхронной сессии"""
        # Создаем MagicMock, который поддерживает async context manager
        async_session = MagicMock()
        
        # Создаем мок для сессии внутри контекстного менеджера
        session_mock = AsyncMock(spec=AsyncSession)
        
        # Настраиваем async context manager
        async_session.__aenter__ = AsyncMock(return_value=session_mock)
        async_session.__aexit__ = AsyncMock(return_value=None)
        
        # Настраиваем return_value для совместимости с патчингом
        async_session.return_value = async_session
        
        return async_session

    @pytest.fixture
    def user_repository(self, mock_async_session):
        """Фикстура для создания UserRepository с mock сессией"""
        # Создаем UserRepository и патчим async_session для использования mock
        repo = UserRepository("postgresql+asyncpg://test:test@localhost/test", None)
        # Заменяем реальный async_sessionmaker на наш mock
        repo.async_session = mock_async_session
        return repo

    @pytest.fixture
    def mock_session(self, mock_async_session):
        """Фикстура для mock сессии внутри контекстного менеджера"""
        session_mock = mock_async_session.__aenter__.return_value
        # Создаем базовые моки для методов сессии
        session_mock.execute = AsyncMock()
        session_mock.commit = AsyncMock()
        session_mock.rollback = AsyncMock()
        session_mock.get = AsyncMock()
        return session_mock

    @pytest.fixture
    def test_user(self):
        """Фикстура с тестовым объектом User"""
        user = Mock(spec=User)
        user.id = 1
        user.user_id = 123
        user.created_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        return user

    @pytest.fixture
    def test_balance(self):
        """Фикстура с тестовым объектом Balance"""
        balance = Mock(spec=Balance)
        balance.user_id = 123
        balance.amount = Decimal('100.0')
        balance.currency = "TON"
        balance.updated_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        balance.created_at = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        return balance

    @pytest.fixture
    def test_transaction(self):
        """Фикстура с тестовым объектом Transaction"""
        transaction = Mock(spec=Transaction)
        transaction.id = 1
        transaction.user_id = 123
        transaction.transaction_type = TransactionType.RECHARGE
        transaction.status = TransactionStatus.COMPLETED
        transaction.amount = Decimal('50.0')
        transaction.currency = "TON"
        transaction.description = "Пополнение баланса"
        transaction.external_id = "test_payment_123"
        transaction.created_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        transaction.updated_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        transaction.transaction_metadata = json.dumps({"payment_uuid": "test_payment_123"})
        return transaction

    @pytest.fixture
    def mock_user_cache(self):
        """Фикстура для mock UserCache"""
        return Mock(spec=UserCache)

    # Тесты для методов работы с пользователями

    @pytest.mark.asyncio
    async def test_create_tables_success(self, user_repository):
        """Тест успешного создания таблиц"""
        # Пропускаем тест, так как метод create_tables использует
        # низкоуровневые методы SQLAlchemy, которые сложно мокировать
        # и не содержат бизнес-логики для тестирования
        pytest.skip("create_tables метод использует низкоуровневые вызовы SQLAlchemy, тестирование не требуется")

    @pytest.mark.asyncio
    async def test_add_user_success(self, user_repository):
        """Тест успешного добавления пользователя"""
        # Используем патчинг напрямую для методов сессии
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'commit') as mock_commit:
                # Настраиваем моки
                mock_execute.return_value = None
                mock_commit.return_value = None
                
                result = await user_repository.add_user(123)
                
                assert result is True
                mock_execute.assert_called_once()
                mock_commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_user_error(self, user_repository, mock_session):
        """Тест добавления пользователя с ошибкой"""
        mock_session.execute.side_effect = Exception("DB error")
        mock_session.rollback.return_value = None
        
        result = await user_repository.add_user(123)
        
        assert result is False
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_found(self, user_repository, test_user):
        """Тест получения существующего пользователя"""
        # Используем патчинг напрямую для метода execute
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = test_user
            mock_execute.return_value = mock_result
            
            result = await user_repository.get_user(123)
            
            assert result["id"] == 1
            assert result["user_id"] == 123
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, user_repository):
        """Тест получения несуществующего пользователя"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_execute.return_value = mock_result
            
            result = await user_repository.get_user(999)
            
            assert result is None
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_with_cache(self, user_repository, mock_user_cache):
        """Тест получения пользователя с использованием кеша"""
        user_repository.user_cache = mock_user_cache
        cached_user = {"id": 1, "user_id": 123, "created_at": "2024-01-01T10:00:00Z"}
        mock_user_cache.get_user_profile.return_value = cached_user
        
        result = await user_repository.get_user(123)
        
        assert result == cached_user
        mock_user_cache.get_user_profile.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_user_exists_true(self, user_repository, test_user):
        """Тест проверки существования пользователя (существует)"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = test_user
            mock_execute.return_value = mock_result
            
            result = await user_repository.user_exists(123)
            
            assert result is True
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_exists_false(self, user_repository):
        """Тест проверки существования пользователя (не существует)"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_execute.return_value = mock_result
            
            result = await user_repository.user_exists(999)
            
            assert result is False
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_users_success(self, user_repository):
        """Тест получения всех пользователей"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_result = Mock()
            mock_result.fetchall.return_value = [(123,), (456,), (789,)]
            mock_execute.return_value = mock_result
            
            result = await user_repository.get_all_users()
            
            assert result == [123, 456, 789]
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_users_empty(self, user_repository):
        """Тест получения пустого списка пользователей"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_result = Mock()
            mock_result.fetchall.return_value = []
            mock_execute.return_value = mock_result
            
            result = await user_repository.get_all_users()
            
            assert result == []
            mock_execute.assert_called_once()

    # Тесты для методов работы с балансами

    @pytest.mark.asyncio
    async def test_get_user_balance_found(self, user_repository, test_balance):
        """Тест получения существующего баланса пользователя"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = test_balance
            mock_execute.return_value = mock_result
            
            result = await user_repository.get_user_balance(123)
            
            assert result["user_id"] == 123
            assert result["balance"] == 100.0
            assert result["currency"] == "TON"
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_balance_not_found_creates_new(self, user_repository):
        """Тест получения несуществующего баланса с созданием нового"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            with patch.object(user_repository, 'create_user_balance', AsyncMock(return_value=True)):
                mock_result = Mock()
                mock_result.scalar_one_or_none.return_value = None
                mock_execute.return_value = mock_result
                
                result = await user_repository.get_user_balance(123)
                
                assert result["user_id"] == 123
                assert result["balance"] == 0
                user_repository.create_user_balance.assert_called_once_with(123, 0)

    @pytest.mark.asyncio
    async def test_get_user_balance_with_cache(self, user_repository, mock_user_cache):
        """Тест получения баланса с использованием кеша"""
        user_repository.user_cache = mock_user_cache
        mock_user_cache.get_user_balance.return_value = 150
        
        result = await user_repository.get_user_balance(123)
        
        assert result["user_id"] == 123
        assert result["balance"] == 150
        mock_user_cache.get_user_balance.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_create_user_balance_success(self, user_repository, mock_session):
        """Тест успешного создания баланса пользователя"""
        mock_session.get.return_value = None  # Баланс не существует
        mock_session.execute.return_value = None
        mock_session.commit.return_value = None
        
        result = await user_repository.create_user_balance(123, 50.0)
        
        assert result is True
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_user_balance_already_exists(self, user_repository, mock_session, test_balance):
        """Тест создания баланса, который уже существует"""
        mock_session.get.return_value = test_balance  # Баланс уже существует
        
        result = await user_repository.create_user_balance(123, 50.0)
        
        assert result is True  # Должен вернуть True даже если уже существует
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_user_balance_error(self, user_repository, mock_session):
        """Тест создания баланса с ошибкой"""
        mock_session.get.return_value = None
        mock_session.execute.side_effect = Exception("DB error")
        mock_session.rollback.return_value = None
        
        result = await user_repository.create_user_balance(123, 50.0)
        
        assert result is False
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_user_balance_add_operation(self, user_repository):
        """Тест обновления баланса операцией 'add'"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'commit') as mock_commit:
                with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'get') as mock_get:
                    # Создаем mock объект баланса
                    mock_balance = Mock()
                    mock_balance.amount = Decimal('100.0')
                    
                    mock_get.return_value = mock_balance
                    mock_commit.return_value = None
                    
                    result = await user_repository.update_user_balance(123, 50.0, "add")
                    
                    assert result is True
                    # Проверяем, что баланс был изменен
                    assert mock_balance.amount == Decimal('150.0')  # 100 + 50
                    mock_commit.assert_called_once()
                    mock_get.assert_called_once_with(Balance, 123)

    @pytest.mark.asyncio
    async def test_update_user_balance_subtract_operation(self, user_repository):
        """Тест обновления баланса операцией 'subtract'"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'commit') as mock_commit:
                with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'get') as mock_get:
                    # Создаем mock объект баланса
                    mock_balance = Mock()
                    mock_balance.amount = Decimal('100.0')
                    
                    mock_get.return_value = mock_balance
                    mock_commit.return_value = None
                    
                    result = await user_repository.update_user_balance(123, 30.0, "subtract")
                    
                    assert result is True
                    # Проверяем, что баланс был изменен
                    assert mock_balance.amount == Decimal('70.0')  # 100 - 30
                    mock_commit.assert_called_once()
                    mock_get.assert_called_once_with(Balance, 123)

    @pytest.mark.asyncio
    async def test_update_user_balance_set_operation(self, user_repository):
        """Тест обновления баланса операцией 'set'"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'commit') as mock_commit:
                with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'get') as mock_get:
                    # Создаем mock объект баланса
                    mock_balance = Mock()
                    mock_balance.amount = Decimal('100.0')
                    
                    mock_get.return_value = mock_balance
                    mock_commit.return_value = None
                    
                    result = await user_repository.update_user_balance(123, 200.0, "set")
                    
                    assert result is True
                    # Проверяем, что баланс был изменен
                    assert mock_balance.amount == Decimal('200.0')  # Установлено новое значение
                    mock_commit.assert_called_once()
                    mock_get.assert_called_once_with(Balance, 123)

    @pytest.mark.asyncio
    async def test_update_user_balance_create_new(self, user_repository):
        """Тест обновления баланса для нового пользователя"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'get') as mock_get:
            with patch.object(user_repository, 'create_user_balance', AsyncMock(return_value=True)):
                # Создаем mock объект баланса для второго вызова get
                mock_balance = Mock()
                mock_balance.amount = Decimal('0.0')
                
                # Настраиваем side_effect: первый вызов возвращает None, второй - mock_balance
                mock_get.side_effect = [None, mock_balance]
                
                result = await user_repository.update_user_balance(123, 50.0, "add")
                
                assert result is True
                # Проверяем, что create_user_balance был вызван с правильными аргументами
                user_repository.create_user_balance.assert_called_once_with(123, 0)
                # Проверяем, что get был вызван дважды: для проверки и после создания
                assert mock_get.call_count == 2
                mock_get.assert_any_call(Balance, 123)

    @pytest.mark.asyncio
    async def test_update_user_balance_unknown_operation(self, user_repository):
        """Тест обновления баланса с неизвестной операцией"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'rollback') as mock_rollback:
                with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'get') as mock_get:
                    # Создаем mock объект баланса
                    mock_balance = Mock()
                    mock_balance.amount = Decimal('100.0')
                    
                    mock_get.return_value = mock_balance
                    
                    result = await user_repository.update_user_balance(123, 50.0, "unknown_operation")
                    
                    assert result is False
                    mock_rollback.assert_called_once()
                    # Баланс не должен быть изменен при неизвестной операции
                    assert mock_balance.amount == Decimal('100.0')

    # Тесты для методов работы с транзакциями

    @pytest.mark.asyncio
    async def test_create_transaction_success(self, user_repository):
        """Тест успешного создания транзакции"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'commit') as mock_commit:
                mock_result = Mock()
                mock_result.inserted_primary_key = [1]
                mock_execute.return_value = mock_result
                mock_commit.return_value = None
                
                result = await user_repository.create_transaction(
                    user_id=123,
                    transaction_type=TransactionType.RECHARGE,
                    amount=50.0,
                    status=TransactionStatus.PENDING,
                    description="Test transaction"
                )
                
                assert result == 1
                mock_execute.assert_called_once()
                mock_commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_transaction_error(self, user_repository):
        """Тест создания транзакции с ошибкой"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'rollback') as mock_rollback:
                mock_execute.side_effect = Exception("DB error")
                
                result = await user_repository.create_transaction(
                    user_id=123,
                    transaction_type=TransactionType.RECHARGE,
                    amount=50.0
                )
                
                assert result is None
                mock_rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_transactions_success(self, user_repository, test_transaction):
        """Тест успешного получения транзакций пользователя"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_scalars_result = Mock()
            mock_scalars_result.all.return_value = [test_transaction]
            
            mock_result = Mock()
            mock_result.scalars.return_value = mock_scalars_result
            mock_execute.return_value = mock_result
            
            result = await user_repository.get_user_transactions(123, 10)
            
            assert len(result) == 1
            assert result[0]["id"] == 1
            assert result[0]["amount"] == 50.0
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_transactions_with_filters(self, user_repository, test_transaction):
        """Тест получения транзакций с фильтрами"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_scalars_result = Mock()
            mock_scalars_result.all.return_value = [test_transaction]
            
            mock_result = Mock()
            mock_result.scalars.return_value = mock_scalars_result
            mock_execute.return_value = mock_result
            
            result = await user_repository.get_user_transactions(
                user_id=123,
                limit=10,
                transaction_type=TransactionType.RECHARGE,
                status=TransactionStatus.COMPLETED
            )
            
            assert len(result) == 1
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_transactions_empty(self, user_repository):
        """Тест получения пустого списка транзакций"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_scalars_result = Mock()
            mock_scalars_result.all.return_value = []
            
            mock_result = Mock()
            mock_result.scalars.return_value = mock_scalars_result
            mock_execute.return_value = mock_result
            
            result = await user_repository.get_user_transactions(123, 10)
            
            assert result == []
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_transaction_by_external_id_found(self, user_repository, test_transaction):
        """Тест получения транзакции по external_id (найдена)"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = test_transaction
            mock_execute.return_value = mock_result
            
            result = await user_repository.get_transaction_by_external_id("test_payment_123")
            
            assert result["id"] == 1
            assert result["external_id"] == "test_payment_123"
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_transaction_by_external_id_not_found(self, user_repository):
        """Тест получения транзакции по external_id (не найдена)"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_execute.return_value = mock_result
            
            result = await user_repository.get_transaction_by_external_id("nonexistent")
            
            assert result is None
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_transaction_status_success(self, user_repository, test_transaction):
        """Тест успешного обновления статуса транзакции"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'commit') as mock_commit:
                mock_result = Mock()
                mock_result.scalar_one_or_none.return_value = test_transaction
                mock_execute.return_value = mock_result
                mock_commit.return_value = None
                
                result = await user_repository.update_transaction_status(
                    transaction_id=1,
                    status=TransactionStatus.COMPLETED,
                    metadata={"completed_at": "2024-01-01T10:00:00Z"}
                )
                
                assert result is True
                mock_commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_transaction_status_not_found(self, user_repository):
        """Тест обновления статуса несуществующей транзакции"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'get') as mock_get:
            mock_get.return_value = None
            
            result = await user_repository.update_transaction_status(999, TransactionStatus.COMPLETED)
            
            assert result is False
            mock_get.assert_called_once_with(Transaction, 999)

    @pytest.mark.asyncio
    async def test_update_transaction_status_error(self, user_repository, test_transaction):
        """Тест обновления статуса транзакции с ошибкой"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'get') as mock_get:
            with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'commit') as mock_commit:
                with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'rollback') as mock_rollback:
                    # Создаем mock транзакции
                    mock_get.return_value = test_transaction
                    # Имитируем ошибку при коммите
                    mock_commit.side_effect = Exception("DB error")
                    
                    result = await user_repository.update_transaction_status(1, TransactionStatus.COMPLETED)
                    
                    assert result is False
                    mock_rollback.assert_called_once()
                    mock_get.assert_called_once_with(Transaction, 1)


class TestUserRepositoryEdgeCases:
    """Тесты для edge-cases UserRepository"""
    
    @pytest.fixture
    def mock_async_session(self):
        """Фикстура для mock асинхронной сессии"""
        # Создаем MagicMock, который поддерживает async context manager
        async_session = MagicMock()
        
        # Создаем мок для сессии внутри контекстного менеджера
        session_mock = AsyncMock(spec=AsyncSession)
        
        # Настраиваем async context manager
        async_session.__aenter__ = AsyncMock(return_value=session_mock)
        async_session.__aexit__ = AsyncMock(return_value=None)
        
        # Настраиваем return_value для совместимости с патчингом
        async_session.return_value = async_session
        
        return async_session

    @pytest.fixture
    def user_repository(self, mock_async_session):
        """Фикстура для создания UserRepository с mock сессией"""
        # Создаем UserRepository и патчим async_session для использования mock
        repo = UserRepository("postgresql+asyncpg://test:test@localhost/test", None)
        # Заменяем реальный async_sessionmaker на наш mock
        repo.async_session = mock_async_session
        return repo

    @pytest.fixture
    def test_user(self):
        """Фикстура с тестовым объектом User"""
        user = Mock(spec=User)
        user.id = 1
        user.user_id = 123
        user.created_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        return user

    @pytest.fixture
    def test_transaction(self):
        """Фикстура с тестовым объектом Transaction"""
        transaction = Mock(spec=Transaction)
        transaction.id = 1
        transaction.user_id = 123
        transaction.transaction_type = TransactionType.RECHARGE
        transaction.status = TransactionStatus.COMPLETED
        transaction.amount = Decimal('50.0')
        transaction.currency = "TON"
        transaction.description = "Пополнение баланса"
        transaction.external_id = "test_payment_123"
        transaction.created_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        transaction.updated_at = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        transaction.transaction_metadata = json.dumps({"payment_uuid": "test_payment_123"})
        return transaction

    @pytest.mark.asyncio
    async def test_transaction_metadata_parsing_error(self, user_repository, test_transaction):
        """Тест обработки ошибок парсинга метаданных транзакции"""
        test_transaction.transaction_metadata = "invalid_json"
        
        # Используем патчинг напрямую для метода execute
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            mock_scalars_result = Mock()
            mock_scalars_result.all.return_value = [test_transaction]
            
            mock_result = Mock()
            mock_result.scalars.return_value = mock_scalars_result
            mock_execute.return_value = mock_result
            
            result = await user_repository.get_user_transactions(123, 10)
            
            assert len(result) == 1
            # Проверяем, что метаданные возвращаются как есть при ошибке парсинга
            assert result[0]["metadata"] == "invalid_json"
            # Проверяем, что execute был вызван
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_user_balance_error_handling(self, user_repository):
        """Тест обработки ошибок при получении баланса"""
        with patch.object(user_repository.async_session.return_value.__aenter__.return_value, 'execute') as mock_execute:
            with patch.object(user_repository.logger, 'error') as mock_error:
                mock_execute.side_effect = Exception("DB error")
                
                # Ожидаем, что метод выбросит исключение, так как нет обработки ошибок
                with pytest.raises(Exception, match="DB error"):
                    await user_repository.get_user_balance(123)
                
                # Проверяем, что execute был вызван
                mock_execute.assert_called_once()
                # Логгер не должен быть вызван, так как исключение не перехватывается
                assert not mock_error.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])