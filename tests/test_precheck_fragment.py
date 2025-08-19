"""
Tests for Fragment API pre-check script
"""
import pytest
import sys
from unittest.mock import patch, mock_open
import os

# Добавляем путь к скриптам
sys.path.insert(0, 'scripts')

from scripts.precheck_fragment import check_seed_phrase_format, check_fragment_cookies, check_auto_refresh_setting


class TestPrecheckFragment:
    """Tests for Fragment API pre-check"""
    
    def test_check_seed_phrase_format_valid(self):
        """Test valid seed phrase format"""
        valid_seed = "word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12 word13 word14 word15 word16 word17 word18 word19 word20 word21 word22 word23 word24"
        assert check_seed_phrase_format(valid_seed) == True
    
    def test_check_seed_phrase_format_invalid_length(self):
        """Test invalid seed phrase length"""
        invalid_seed = "word1 word2 word3"
        with patch('builtins.print') as mock_print:
            result = check_seed_phrase_format(invalid_seed)
            assert result == False
            mock_print.assert_called()  # Проверяем, что была вызвана печать ошибки
    
    def test_check_seed_phrase_format_empty(self):
        """Test empty seed phrase"""
        with patch('builtins.print') as mock_print:
            result = check_seed_phrase_format("")
            assert result == False
            mock_print.assert_called()  # Проверяем, что была вызвана печать ошибки
    
    def test_check_seed_phrase_format_default_value(self):
        """Test default seed phrase value"""
        with patch('builtins.print') as mock_print:
            result = check_seed_phrase_format("your_24_words_seed_phrase")
            assert result == False
            mock_print.assert_called()  # Проверяем, что была вызвана печать ошибки
    
    def test_check_fragment_cookies_valid(self):
        """Test valid cookies"""
        valid_cookies = "cookie1=value1; cookie2=value2"
        with patch('builtins.print') as mock_print:
            result = check_fragment_cookies(valid_cookies)
            assert result == True
            # Для валидных cookies тоже может быть вызван print, проверяем что нет ошибок
    
    def test_check_fragment_cookies_empty(self):
        """Test empty cookies"""
        with patch('builtins.print') as mock_print:
            result = check_fragment_cookies("")
            assert result == False  # Даже если cookies пустые, функция возвращает False
            mock_print.assert_called()  # Проверяем, что была вызвана печать предупреждения
    
    def test_check_fragment_cookies_default_value(self):
        """Test default cookies value"""
        with patch('builtins.print') as mock_print:
            result = check_fragment_cookies("your_fragment_cookies")
            assert result == False
            mock_print.assert_called()  # Проверяем, что была вызвана печать ошибки
    
    def test_check_auto_refresh_setting_enabled(self):
        """Test auto refresh setting enabled"""
        with patch.dict(os.environ, {'FRAGMENT_AUTO_COOKIE_REFRESH': 'true'}), \
             patch('builtins.print') as mock_print:
            result = check_auto_refresh_setting()
            assert result == True
            mock_print.assert_called()  # Проверяем, что была вызвана печать
    
    def test_check_auto_refresh_setting_disabled(self):
        """Test auto refresh setting disabled"""
        with patch.dict(os.environ, {'FRAGMENT_AUTO_COOKIE_REFRESH': 'false'}), \
             patch('builtins.print') as mock_print:
            result = check_auto_refresh_setting()
            assert result == True  # Функция всегда возвращает True
            mock_print.assert_called()  # Проверяем, что была вызвана печать
    
    def test_check_auto_refresh_setting_not_set(self):
        """Test auto refresh setting not set"""
        with patch.dict(os.environ, {}, clear=True), \
             patch('builtins.print') as mock_print:
            result = check_auto_refresh_setting()
            assert result == True  # Функция всегда возвращает True
            mock_print.assert_called()  # Проверяем, что была вызвана печать


if __name__ == "__main__":
    pytest.main([__file__])