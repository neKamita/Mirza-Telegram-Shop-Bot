"""
Unit tests for PaymentCache service
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from datetime import datetime, timedelta, timezone
from services.cache.payment_cache import PaymentCache, LocalCache


class TestLocalCache:
    """Unit tests for LocalCache class"""

    def test_local_cache_init(self):
        """Test LocalCache initialization"""
        cache = LocalCache(max_size=100, ttl=60)
        assert cache.max_size == 100
        assert cache.ttl == 60
        assert cache.cache == {}
        assert cache.access_times == {}

    def test_local_cache_set_get(self):
        """Test setting and getting values from local cache"""
        cache = LocalCache()
        test_data = {"key": "value", "number": 42}
        
        # Set value
        result = cache.set("test_key", test_data)
        assert result is True
        
        # Get value - LocalCache wraps data in {'data': value} structure
        retrieved = cache.get("test_key")
        assert retrieved == {"data": test_data}
        
        # Test non-existent key
        assert cache.get("non_existent") is None

    def test_local_cache_expiration(self):
        """Test local cache expiration"""
        cache = LocalCache(ttl=1)  # 1 second TTL
        
        # Set value
        cache.set("test_key", {"data": "value"})
        
        # Should be available immediately
        assert cache.get("test_key") is not None
        
        # Wait for expiration
        import time
        time.sleep(1.1)
        
        # Should be expired
        assert cache.get("test_key") is None

    def test_local_cache_cleanup(self):
        """Test automatic cleanup of expired entries"""
        cache = LocalCache(max_size=2, ttl=1)  # Small size and 1 second TTL
        
        # Add multiple entries
        cache.set("key1", {"data": "value1"})
        cache.set("key2", {"data": "value2"})
        
        # Wait for expiration
        import time
        time.sleep(1.1)
        
        # Add another entry to trigger cleanup
        cache.set("key3", {"data": "value3"})
        
        # Only key3 should remain
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is not None


class TestPaymentCache:
    """Unit tests for PaymentCache service"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client fixture"""
        mock = AsyncMock()
        # Mock common Redis methods
        mock.get = AsyncMock()
        mock.setex = AsyncMock()
        mock.delete = AsyncMock()
        mock.keys = AsyncMock()
        mock.lrange = AsyncMock()
        mock.lpush = AsyncMock()
        mock.lrem = AsyncMock()
        mock.expire = AsyncMock()
        mock.exists = AsyncMock()
        return mock

    @pytest.fixture
    def payment_cache(self, mock_redis):
        """PaymentCache instance with mock Redis"""
        return PaymentCache(mock_redis)

    @pytest.fixture
    def payment_cache_no_redis(self):
        """PaymentCache instance without Redis"""
        return PaymentCache(None)

    @pytest.fixture
    def sample_invoice_data(self):
        """Sample invoice data for testing"""
        return {
            "invoice_id": "inv_12345",
            "amount": 100.0,
            "currency": "USD",
            "status": "pending",
            "created_at": "2024-01-01T00:00:00"
        }

    @pytest.fixture
    def sample_payment_data(self):
        """Sample payment data for testing"""
        return {
            "payment_id": "pay_67890",
            "amount": 50.0,
            "currency": "USD",
            "description": "Test payment"
        }

    @pytest.mark.asyncio
    async def test_cache_invoice_success(self, payment_cache, mock_redis, sample_invoice_data):
        """Test successful invoice caching with Redis"""
        # Mock Redis setex to succeed
        mock_redis.setex.return_value = True
        
        result = await payment_cache.cache_invoice("test_invoice", sample_invoice_data)
        
        assert result is True
        mock_redis.setex.assert_called_once()
        
        # PaymentCache only saves to local cache if Redis fails or when getting data
        # So local cache should be empty after successful Redis operation
        if payment_cache.local_cache:
            local_data = payment_cache.local_cache.get("invoice:test_invoice")
            assert local_data is None  # Should not be in local cache after Redis success

    @pytest.mark.asyncio
    async def test_cache_invoice_redis_failure_local_success(self, payment_cache, mock_redis, sample_invoice_data):
        """Test invoice caching with Redis failure but local cache success"""
        # Mock Redis to fail
        mock_redis.setex.side_effect = Exception("Redis error")
        
        result = await payment_cache.cache_invoice("test_invoice", sample_invoice_data)
        
        # Should succeed with local cache
        assert result is True
        
        # LocalCache wraps data in {'data': value} structure
        local_data = payment_cache.local_cache.get("invoice:test_invoice")
        assert local_data is not None
        assert 'data' in local_data
        assert local_data['data']['invoice_id'] == sample_invoice_data['invoice_id']
        assert local_data['data']['amount'] == sample_invoice_data['amount']
        # cached_at is removed before saving to local cache as it's a temporary field

    @pytest.mark.asyncio
    async def test_cache_invoice_no_redis_no_local(self, payment_cache_no_redis, sample_invoice_data):
        """Test invoice caching without Redis and local cache disabled"""
        # Disable local cache
        payment_cache_no_redis.local_cache_enabled = False
        payment_cache_no_redis.local_cache = None
        
        result = await payment_cache_no_redis.cache_invoice("test_invoice", sample_invoice_data)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_invoice_redis_success(self, payment_cache, mock_redis, sample_invoice_data):
        """Test getting invoice from Redis successfully"""
        # Mock Redis to return valid data
        redis_data = sample_invoice_data.copy()
        redis_data['cached_at'] = datetime.now(timezone.utc).isoformat()
        serialized_data = json.dumps(redis_data)
        mock_redis.get.return_value = serialized_data
        
        # Debug: check what Redis mock returns
        print(f"Redis mock returns: {mock_redis.get.return_value}")
        print(f"Serialized data type: {type(serialized_data)}")
        
        result = await payment_cache.get_invoice("test_invoice")
        
        print(f"PaymentCache result: {result}")
        print(f"Expected: {sample_invoice_data}")
        
        assert result == sample_invoice_data
        mock_redis.get.assert_called_once_with("invoice:test_invoice")

    @pytest.mark.asyncio
    async def test_get_invoice_redis_expired(self, payment_cache, mock_redis, sample_invoice_data):
        """Test getting expired invoice from Redis"""
        # Mock Redis to return expired data
        expired_data = sample_invoice_data.copy()
        expired_data['cached_at'] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        mock_redis.get.return_value = json.dumps(expired_data)
        
        result = await payment_cache.get_invoice("test_invoice")
        
        assert result is None
        mock_redis.delete.assert_called_once_with("invoice:test_invoice")

    @pytest.mark.asyncio
    async def test_get_invoice_redis_failure_local_fallback(self, payment_cache, mock_redis, sample_invoice_data):
        """Test getting invoice with Redis failure and local cache fallback"""
        # Mock Redis to fail
        mock_redis.get.side_effect = Exception("Redis error")
        
        # Pre-populate local cache - use the full key with prefix that get_invoice expects
        key = f"{payment_cache.INVOICE_PREFIX}test_invoice"
        payment_cache.local_cache.set(key, sample_invoice_data)
        
        result = await payment_cache.get_invoice("test_invoice")
        
        # Debug: check what LocalCache returns and what get_invoice returns
        print(f"LocalCache.get('{key}'): {payment_cache.local_cache.get(key)}")
        print(f"get_invoice result: {result}")
        print(f"Expected: {sample_invoice_data}")
        
        # get_invoice should extract the data from LocalCache's wrapped structure
        assert result == sample_invoice_data

    @pytest.mark.asyncio
    async def test_cache_payment_status(self, payment_cache, mock_redis):
        """Test caching payment status"""
        mock_redis.setex.return_value = True
        
        result = await payment_cache.cache_payment_status(
            "test_payment", 
            "completed",
            {"transaction_id": "txn_123"}
        )
        
        assert result is True
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_payment_status(self, payment_cache, mock_redis):
        """Test getting payment status"""
        status_data = {
            "status": "completed",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "transaction_id": "txn_123"
        }
        mock_redis.get.return_value = json.dumps(status_data)
        
        result = await payment_cache.get_payment_status("test_payment")
        
        assert result["status"] == "completed"
        assert "updated_at" not in result  # Should be removed

    @pytest.mark.asyncio
    async def test_cache_payment_details(self, payment_cache, mock_redis, sample_payment_data):
        """Test caching payment details"""
        mock_redis.setex.return_value = True
        
        result = await payment_cache.cache_payment_details("test_payment", sample_payment_data)
        
        assert result is True
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_payment_details(self, payment_cache, mock_redis, sample_payment_data):
        """Test getting payment details"""
        payment_data = sample_payment_data.copy()
        payment_data['cached_at'] = datetime.now(timezone.utc).isoformat()
        mock_redis.get.return_value = json.dumps(payment_data)
        
        result = await payment_cache.get_payment_details("test_payment")
        
        assert result == sample_payment_data
        assert "cached_at" not in result  # Should be removed

    @pytest.mark.asyncio
    async def test_update_payment_status(self, payment_cache, mock_redis):
        """Test updating payment status"""
        mock_redis.setex.return_value = True
        
        result = await payment_cache.update_payment_status(
            "test_payment", 
            "processing",
            {"reason": "started_processing"}
        )
        
        assert result is True
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_payment_cache(self, payment_cache, mock_redis):
        """Test invalidating payment cache"""
        mock_redis.keys.return_value = [b"payment:test_payment", b"invoice:test_payment"]
        mock_redis.delete.return_value = 2
        
        result = await payment_cache.invalidate_payment_cache("test_payment")
        
        assert result is True
        assert mock_redis.delete.call_count >= 1

    @pytest.mark.asyncio
    async def test_get_payments_by_status(self, payment_cache, mock_redis):
        """Test getting payments by status"""
        # Mock Redis to return payment IDs
        mock_redis.lrange.return_value = [b"pay_1", b"pay_2"]
        
        # Mock get_payment_status to return status data
        with patch.object(payment_cache, 'get_payment_status') as mock_status:
            with patch.object(payment_cache, 'get_payment_details') as mock_details:
                mock_status.return_value = {"status": "completed"}
                mock_details.return_value = {"amount": 100}
                
                result = await payment_cache.get_payments_by_status("completed", limit=10)
                
                assert len(result) == 2
                assert result[0]['payment_id'] == "pay_1"

    @pytest.mark.asyncio
    async def test_get_payment_stats(self, payment_cache, mock_redis):
        """Test getting payment statistics"""
        mock_redis.keys.return_value = [b"payment_status:pay_1", b"payment_status:pay_2"]
        
        with patch.object(payment_cache, 'get_payment_status') as mock_status:
            mock_status.return_value = {
                "status": "completed",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            result = await payment_cache.get_payment_stats()
            
            assert result['total_cached_payments'] == 2
            assert 'completed' in result['payments_by_status']

    @pytest.mark.asyncio
    async def test_is_payment_cached(self, payment_cache, mock_redis):
        """Test checking if payment is cached"""
        mock_redis.exists.return_value = 1
        
        result = await payment_cache.is_payment_cached("test_payment")
        
        assert result is True
        mock_redis.exists.assert_called_once_with("payment_status:test_payment")

    @pytest.mark.asyncio
    async def test_extend_payment_cache(self, payment_cache, mock_redis):
        """Test extending payment cache TTL"""
        mock_redis.expire.return_value = True
        
        result = await payment_cache.extend_payment_cache("test_payment", additional_ttl=600)
        
        assert result is True
        assert mock_redis.expire.call_count >= 1

    @pytest.mark.asyncio
    async def test_cache_payment_transaction(self, payment_cache, mock_redis, sample_payment_data):
        """Test caching payment transaction"""
        mock_redis.setex.return_value = True
        
        result = await payment_cache.cache_payment_transaction("test_payment", sample_payment_data)
        
        assert result is True
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_payment_transaction(self, payment_cache, mock_redis, sample_payment_data):
        """Test getting payment transaction"""
        transaction_data = sample_payment_data.copy()
        transaction_data['cached_at'] = datetime.now(timezone.utc).isoformat()
        mock_redis.get.return_value = json.dumps(transaction_data)
        
        result = await payment_cache.get_payment_transaction("test_payment")
        
        assert result == sample_payment_data

    @pytest.mark.asyncio
    async def test_execute_redis_operation_async(self, payment_cache, mock_redis):
        """Test executing async Redis operation"""
        mock_redis.get.return_value = "test_value"
        
        result = await payment_cache._execute_redis_operation('get', 'test_key')
        
        assert result == "test_value"
        mock_redis.get.assert_called_once_with('test_key')

    @pytest.mark.asyncio
    async def test_execute_redis_operation_sync(self, payment_cache):
        """Test executing sync Redis operation with thread"""
        # Create a mock with sync method
        sync_mock = MagicMock()
        sync_mock.sync_method = MagicMock(return_value="sync_value")
        payment_cache.redis_client = sync_mock
        
        result = await payment_cache._execute_redis_operation('sync_method', 'arg1')
        
        assert result == "sync_value"

    @pytest.mark.asyncio
    async def test_execute_redis_operation_no_client(self, payment_cache_no_redis):
        """Test executing Redis operation without client"""
        with pytest.raises(ConnectionError):
            await payment_cache_no_redis._execute_redis_operation('get', 'test_key')

    @pytest.mark.asyncio
    async def test_update_payment_status_index(self, payment_cache, mock_redis):
        """Test updating payment status index"""
        mock_redis.lpush.return_value = 1
        mock_redis.expire.return_value = True
        
        await payment_cache._update_payment_status_index("test_payment", "completed")
        
        mock_redis.lpush.assert_called_once_with("payment_status_index:completed", "test_payment")
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_payment_from_indices(self, payment_cache, mock_redis):
        """Test removing payment from indices"""
        mock_redis.lrem.return_value = 1
        
        await payment_cache._remove_payment_from_indices("test_payment")
        
        assert mock_redis.lrem.call_count == 5  # For each status


class TestPaymentCacheEdgeCases:
    """Edge case tests for PaymentCache"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client fixture"""
        mock = AsyncMock()
        # Mock common Redis methods
        mock.get = AsyncMock()
        mock.setex = AsyncMock()
        mock.delete = AsyncMock()
        mock.keys = AsyncMock()
        mock.lrange = AsyncMock()
        mock.lpush = AsyncMock()
        mock.lrem = AsyncMock()
        mock.expire = AsyncMock()
        mock.exists = AsyncMock()
        return mock

    @pytest.fixture
    def payment_cache(self, mock_redis):
        """PaymentCache instance with mock Redis"""
        return PaymentCache(mock_redis)

    @pytest.fixture
    def payment_cache_no_redis(self):
        """PaymentCache instance without Redis"""
        return PaymentCache(None)

    @pytest.fixture
    def sample_invoice_data(self):
        """Sample invoice data for testing"""
        return {
            "invoice_id": "inv_12345",
            "amount": 100.0,
            "currency": "USD",
            "status": "pending",
            "created_at": "2024-01-01T00:00:00"
        }

    @pytest.mark.asyncio
    async def test_get_invoice_invalid_json(self, payment_cache, mock_redis):
        """Test getting invoice with invalid JSON from Redis"""
        mock_redis.get.return_value = "invalid json"
        
        result = await payment_cache.get_invoice("test_invoice")
        
        assert result is None
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_invoice_missing_cached_at(self, payment_cache, mock_redis, sample_invoice_data):
        """Test getting invoice without cached_at field"""
        invalid_data = sample_invoice_data.copy()
        # Remove cached_at field
        mock_redis.get.return_value = json.dumps(invalid_data)
        
        result = await payment_cache.get_invoice("test_invoice")
        
        assert result is None
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_invoice_redis_empty_response(self, payment_cache, mock_redis):
        """Test getting invoice with empty Redis response"""
        mock_redis.get.return_value = None
        
        result = await payment_cache.get_invoice("test_invoice")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_invoice_exception_handling(self, payment_cache, mock_redis, sample_invoice_data):
        """Test exception handling in cache_invoice"""
        # Make both Redis and local cache fail
        mock_redis.setex.side_effect = Exception("Redis error")
        payment_cache.local_cache = None
        
        result = await payment_cache.cache_invoice("test_invoice", sample_invoice_data)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_graceful_degradation_no_redis(self, payment_cache_no_redis, sample_invoice_data):
        """Test graceful degradation without Redis"""
        # Enable local cache
        payment_cache_no_redis.local_cache_enabled = True
        payment_cache_no_redis.local_cache = LocalCache()
        
        # Cache should work with local cache only
        cache_result = await payment_cache_no_redis.cache_invoice("test_invoice", sample_invoice_data)
        get_result = await payment_cache_no_redis.get_invoice("test_invoice")
        
        # Remove cached_at from expected data since get_invoice removes it
        expected_data = sample_invoice_data.copy()
        if 'cached_at' in expected_data:
            del expected_data['cached_at']
        
        assert cache_result is True
        assert get_result == expected_data


class TestPaymentCacheIntegration:
    """Integration-style tests for PaymentCache"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client fixture"""
        mock = AsyncMock()
        # Mock common Redis methods
        mock.get = AsyncMock()
        mock.setex = AsyncMock()
        mock.delete = AsyncMock()
        mock.keys = AsyncMock()
        mock.lrange = AsyncMock()
        mock.lpush = AsyncMock()
        mock.lrem = AsyncMock()
        mock.expire = AsyncMock()
        mock.exists = AsyncMock()
        return mock

    @pytest.fixture
    def payment_cache(self, mock_redis):
        """PaymentCache instance with mock Redis"""
        return PaymentCache(mock_redis)

    @pytest.fixture
    def sample_invoice_data(self):
        """Sample invoice data for testing"""
        return {
            "invoice_id": "inv_12345",
            "amount": 100.0,
            "currency": "USD",
            "status": "pending",
            "created_at": "2024-01-01T00:00:00"
        }

    @pytest.fixture
    def sample_payment_data(self):
        """Sample payment data for testing"""
        return {
            "payment_id": "pay_67890",
            "amount": 50.0,
            "currency": "USD",
            "description": "Test payment"
        }

    @pytest.mark.asyncio
    async def test_complete_payment_flow(self, payment_cache, mock_redis, sample_invoice_data, sample_payment_data):
        """Test complete payment caching flow"""
        # Mock Redis operations
        mock_redis.setex.return_value = True
        mock_redis.get.side_effect = [
            json.dumps({**sample_invoice_data, 'cached_at': datetime.now(timezone.utc).isoformat()}),
            json.dumps({'status': 'pending', 'updated_at': datetime.now(timezone.utc).isoformat()}),
            json.dumps({**sample_payment_data, 'cached_at': datetime.now(timezone.utc).isoformat()})
        ]
        
        # Cache invoice
        cache_result = await payment_cache.cache_invoice("test_invoice", sample_invoice_data)
        assert cache_result is True
        
        # Get invoice - метод get_invoice должен вернуть данные без cached_at
        invoice_result = await payment_cache.get_invoice("test_invoice")
        
        # Отладочный вывод
        print(f"\nDEBUG: invoice_result = {invoice_result}")
        print(f"DEBUG: sample_invoice_data = {sample_invoice_data}")
        
        # Создаем копию для сравнения без временных полей
        expected_invoice = sample_invoice_data.copy()
        expected_invoice.pop('cached_at', None)  # Удаляем cached_at для сравнения
        print(f"DEBUG: expected_invoice = {expected_invoice}")
        
        assert invoice_result == expected_invoice
        
        # Cache payment status
        status_result = await payment_cache.cache_payment_status("test_payment", "pending")
        assert status_result is True
        
        # Get payment status
        status_data = await payment_cache.get_payment_status("test_payment")
        assert status_data["status"] == "pending"
        
        # Cache payment details
        details_result = await payment_cache.cache_payment_details("test_payment", sample_payment_data)
        assert details_result is True
        
        # Get payment details
        details_data = await payment_cache.get_payment_details("test_payment")
        expected_payment = sample_payment_data.copy()
        assert details_data == expected_payment
        
        # Update status
        update_result = await payment_cache.update_payment_status("test_payment", "completed")
        assert update_result is True
        
        # Invalidate cache
        invalidate_result = await payment_cache.invalidate_payment_cache("test_payment")
        assert invalidate_result is True

    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self, payment_cache, mock_redis):
        """Test concurrent cache operations"""
        mock_redis.setex.return_value = True
        mock_redis.get.return_value = json.dumps({
            'status': 'completed',
            'updated_at': datetime.now(timezone.utc).isoformat()
        })
        
        # Run multiple operations concurrently
        results = await asyncio.gather(
            payment_cache.cache_payment_status("pay1", "pending"),
            payment_cache.cache_payment_status("pay2", "processing"),
            payment_cache.get_payment_status("pay1"),
            payment_cache.get_payment_status("pay2")
        )
        
        assert all(results[:2])  # Cache operations should succeed
        assert results[2]["status"] == "completed"
        assert results[3]["status"] == "completed"