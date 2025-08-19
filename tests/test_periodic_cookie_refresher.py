"""
Tests for FragmentCookieRefresher
"""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, Mock

from scripts.periodic_cookie_refresher import FragmentCookieRefresher


class TestFragmentCookieRefresher:
    """Tests for FragmentCookieRefresher"""
    
    @pytest.fixture
    def refresher(self):
        """Fixture for creating FragmentCookieRefresher instance"""
        return FragmentCookieRefresher()
    
    @pytest.mark.asyncio
    async def test_init(self, refresher):
        """Test FragmentCookieRefresher initialization"""
        assert refresher is not None
        assert hasattr(refresher, 'fragment_service')
        assert hasattr(refresher, 'cookie_manager')
        assert refresher.interval == 3600  # Default interval
        assert refresher.running == False
    
    @pytest.mark.asyncio
    async def test_start_stop(self, refresher):
        """Test starting and stopping the refresher"""
        # Mock the refresh method to avoid actual API calls
        with patch.object(refresher, '_refresh_cookies_if_needed', AsyncMock()):
            # Start the refresher
            task = asyncio.create_task(refresher.start())
            
            # Wait a bit
            await asyncio.sleep(0.1)
            
            # Check that it's running
            assert refresher.running == True
            
            # Stop the refresher
            await refresher.stop()
            
            # Check that it's stopped
            assert refresher.running == False
            
            # Cancel the task
            task.cancel()
    
    @pytest.mark.asyncio
    async def test_refresh_cookies_if_needed_with_no_cookies(self, refresher):
        """Test refreshing cookies when no cookies are saved"""
        # Mock methods
        with patch.object(refresher.cookie_manager, '_load_cookies_from_file', AsyncMock(return_value=None)), \
             patch.object(refresher, '_refresh_cookies', AsyncMock()):
            
            await refresher._refresh_cookies_if_needed()
            
            # Check that refresh was called
            refresher._refresh_cookies.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_refresh_cookies_if_needed_with_expired_cookies(self, refresher):
        """Test refreshing cookies when saved cookies are expired"""
        # Mock methods
        with patch.object(refresher.cookie_manager, '_load_cookies_from_file', AsyncMock(return_value="test_cookies")), \
             patch.object(refresher.cookie_manager, '_are_cookies_expired', AsyncMock(return_value=True)), \
             patch.object(refresher, '_refresh_cookies', AsyncMock()):
            
            await refresher._refresh_cookies_if_needed()
            
            # Check that refresh was called
            refresher._refresh_cookies.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_refresh_cookies_if_needed_with_valid_cookies(self, refresher):
        """Test not refreshing cookies when saved cookies are valid"""
        # Mock methods
        with patch.object(refresher.cookie_manager, '_load_cookies_from_file', AsyncMock(return_value="test_cookies")), \
             patch.object(refresher.cookie_manager, '_are_cookies_expired', AsyncMock(return_value=False)), \
             patch.object(refresher, '_refresh_cookies', AsyncMock()):
            
            await refresher._refresh_cookies_if_needed()
            
            # Check that refresh was not called
            refresher._refresh_cookies.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__])