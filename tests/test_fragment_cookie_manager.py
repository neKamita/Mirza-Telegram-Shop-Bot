import pytest
from services.fragment_cookie_manager import FragmentCookieManager
from services.fragment_service import FragmentService

def test_fragment_cookie_manager_init():
    """Test FragmentCookieManager initialization"""
    service = FragmentService()
    manager = FragmentCookieManager(service)
    assert manager is not None
    assert manager.fragment_service == service
