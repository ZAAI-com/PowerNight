"""
Unit tests for PowerwallConnector API response logging and sanitization.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.powernight.core.powerwall.connector import PowerwallConnector
from src.powernight.utils.logging import PowerNightLogger, LogEntry, ComponentType, OperationType, LogLevel


class TestPowerwallResponseLogging:
    """Test PowerwallConnector API response logging functionality."""

    def test_sanitize_api_response_basic(self):
        """Test basic API response sanitization."""
        connector = PowerwallConnector(email="test@example.com")
        
        # Test basic response
        response = {"value": "test", "status": "ok"}
        sanitized = connector._sanitize_api_response(response)
        
        assert sanitized == response
        assert "value" in sanitized
        assert "status" in sanitized

    def test_sanitize_api_response_sensitive_data(self):
        """Test sanitization of sensitive data."""
        connector = PowerwallConnector(email="test@example.com")
        
        # Test response with sensitive data
        response = {
            "access_token": "secret123",
            "refresh_token": "refresh456",
            "password": "mypassword",
            "email": "user@example.com",
            "api_key": "key789",
            "client_secret": "secret999",
            "normal_field": "safe_value"
        }
        
        sanitized = connector._sanitize_api_response(response)
        
        # Check sensitive fields are redacted
        assert sanitized["access_token"] == "***REDACTED***"
        assert sanitized["refresh_token"] == "***REDACTED***"
        assert sanitized["password"] == "***REDACTED***"
        assert sanitized["api_key"] == "***REDACTED***"
        assert sanitized["client_secret"] == "***REDACTED***"
        
        # Check email is partially masked
        assert sanitized["email"] == "u***@example.com"
        
        # Check normal field is preserved
        assert sanitized["normal_field"] == "safe_value"

    def test_sanitize_api_response_nested_data(self):
        """Test sanitization of nested sensitive data."""
        connector = PowerwallConnector(email="test@example.com")
        
        response = {
            "user": {
                "email": "user@example.com",
                "password": "secret123",
                "profile": {
                    "name": "John Doe",
                    "api_key": "key456"
                }
            },
            "tokens": ["access_token", "refresh_token"]
        }
        
        sanitized = connector._sanitize_api_response(response)
        
        # Check nested sensitive data is redacted
        assert sanitized["user"]["email"] == "u***@example.com"
        assert sanitized["user"]["password"] == "***REDACTED***"
        assert sanitized["user"]["profile"]["api_key"] == "***REDACTED***"
        assert sanitized["user"]["profile"]["name"] == "John Doe"  # Normal field preserved
        
        # Check list items are redacted
        assert sanitized["tokens"] == "***REDACTED***"

    def test_sanitize_api_response_size_limit(self):
        """Test API response size limiting."""
        connector = PowerwallConnector(email="test@example.com")
        
        # Create a large response
        large_response = {"data": "x" * 20000000}  # 20MB string
        
        sanitized = connector._sanitize_api_response(large_response, max_size_bytes=1000)
        
        # Should be truncated
        assert "error" in sanitized
        assert "Response too large" in sanitized["error"]
        assert sanitized["truncated"] is True

    def test_sanitize_api_response_error_handling(self):
        """Test error handling in sanitization."""
        connector = PowerwallConnector(email="test@example.com")
        
        # Test with non-serializable object that will cause JSON serialization to fail
        class NonSerializable:
            def __init__(self):
                self.circular_ref = self
        
        response = NonSerializable()
        
        # Mock json.dumps to raise an exception
        with patch('json.dumps', side_effect=TypeError("Object not JSON serializable")):
            sanitized = connector._sanitize_api_response(response)
            
            # Should handle error gracefully
            assert "error" in sanitized
            assert "Failed to sanitize response" in sanitized["error"]

    def test_log_api_response_success(self):
        """Test successful API response logging."""
        connector = PowerwallConnector(email="test@example.com")
        
        # Mock the logger
        mock_logger = Mock()
        connector.logger = mock_logger
        
        response = {"status": "success", "data": "test"}
        
        connector._log_api_response(
            "test_operation",
            response,
            success=True,
            test_param="value"
        )
        
        # Verify logger was called
        mock_logger.log_powerwall_operation.assert_called_once()
        call_args = mock_logger.log_powerwall_operation.call_args
        
        assert call_args[1]["operation"] == "test_operation"
        assert call_args[1]["success"] is True
        assert "api_response" in call_args[1]["metadata"]
        assert "response_size_bytes" in call_args[1]["metadata"]
        assert call_args[1]["metadata"]["test_param"] == "value"

    def test_log_api_response_error(self):
        """Test error API response logging."""
        connector = PowerwallConnector(email="test@example.com")
        
        # Mock the logger
        mock_logger = Mock()
        connector.logger = mock_logger
        
        response = {"error": "Something went wrong"}
        
        connector._log_api_response(
            "test_operation",
            response,
            success=False,
            error_details="Test error"
        )
        
        # Verify logger was called
        mock_logger.log_powerwall_operation.assert_called_once()
        call_args = mock_logger.log_powerwall_operation.call_args
        
        assert call_args[1]["operation"] == "test_operation"
        assert call_args[1]["success"] is False
        assert call_args[1]["error_details"] == "Test error"

    def test_log_api_response_fallback(self):
        """Test fallback logging when response logging fails."""
        connector = PowerwallConnector(email="test@example.com")
        
        # Mock the logger
        mock_logger = Mock()
        connector.logger = mock_logger
        
        # Mock sanitize_api_response to raise an exception
        with patch.object(connector, '_sanitize_api_response', side_effect=Exception("Sanitization failed")):
            connector._log_api_response(
                "test_operation",
                {"data": "test"},
                success=True
            )
        
        # Should call fallback logging
        mock_logger.log_powerwall_operation.assert_called_once()
        call_args = mock_logger.log_powerwall_operation.call_args
        
        assert call_args[1]["operation"] == "test_operation_response_log_failed"
        assert call_args[1]["success"] is False
        assert "Failed to log response" in call_args[1]["error_details"]


class TestLoggingInfrastructure:
    """Test logging infrastructure enhancements."""

    def test_log_entry_with_api_response(self):
        """Test LogEntry with API response fields."""
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            component=ComponentType.POWERWALL,
            operation=OperationType.INFO,
            level=LogLevel.INFO,
            message="Test message",
            api_response={"status": "success"},
            response_size_bytes=1024
        )
        
        assert entry.api_response == {"status": "success"}
        assert entry.response_size_bytes == 1024

    def test_log_entry_to_dict_includes_api_response(self):
        """Test LogEntry.to_dict includes API response fields."""
        entry = LogEntry(
            timestamp=datetime.now().isoformat(),
            component=ComponentType.POWERWALL,
            operation=OperationType.INFO,
            level=LogLevel.INFO,
            message="Test message",
            api_response={"status": "success"},
            response_size_bytes=1024
        )
        
        result = entry.to_dict()
        
        assert "api_response" in result
        assert "response_size_bytes" in result
        assert result["api_response"] == {"status": "success"}
        assert result["response_size_bytes"] == 1024

    def test_powernight_logger_sanitize_api_response(self):
        """Test PowerNightLogger sanitize_api_response method."""
        logger = PowerNightLogger()
        
        response = {
            "access_token": "secret123",
            "email": "user@example.com",
            "normal_field": "safe"
        }
        
        sanitized = logger.sanitize_api_response(response)
        
        assert sanitized["access_token"] == "***REDACTED***"
        assert sanitized["email"] == "u***@example.com"
        assert sanitized["normal_field"] == "safe"

    def test_log_operation_with_api_response(self):
        """Test log_operation with API response parameters."""
        logger = PowerNightLogger()
        
        # Mock the log_entry method to capture the entry
        with patch.object(logger, 'log_entry') as mock_log_entry:
            logger.log_operation(
                component=ComponentType.POWERWALL,
                operation=OperationType.INFO,
                message="Test operation",
                api_response={"status": "success"},
                response_size_bytes=512
            )
        
        # Verify log_entry was called
        mock_log_entry.assert_called_once()
        entry = mock_log_entry.call_args[0][0]
        
        assert entry.api_response == {"status": "success"}
        assert entry.response_size_bytes == 512


class TestApiResponseIntegration:
    """Test integration of API response logging with PowerwallConnector methods."""

    @patch('src.powernight.core.powerwall.connector.pypowerwall.Powerwall')
    def test_connect_logs_vitals_response(self, mock_powerwall_class):
        """Test that connect() logs the vitals response."""
        # Setup mock
        mock_powerwall = Mock()
        mock_powerwall_class.return_value = mock_powerwall
        mock_powerwall.vitals.return_value = {
            "battery": {"percentage": 85, "charging": True},
            "grid": {"connected": True}
        }
        
        # Mock OAuth manager
        with patch('src.powernight.core.auth.tesla_oauth.TeslaOAuthManager') as mock_oauth:
            mock_oauth.return_value.get_valid_access_token.return_value = "test_token"
            
            connector = PowerwallConnector(email="test@example.com")
            
            # Mock the logger
            with patch.object(connector, '_log_api_response') as mock_log:
                connector.connect()
                
                # Verify API response was logged
                mock_log.assert_called_once()
                call_args = mock_log.call_args
                
                # Check that the method was called with the expected operation name
                assert call_args[0][0] == "cloud_connect_success"  # operation

    @patch('src.powernight.core.powerwall.connector.pypowerwall.Powerwall')
    def test_get_backup_reserve_logs_response(self, mock_powerwall_class):
        """Test that get_backup_reserve_percentage() logs the response."""
        # Setup mock
        mock_powerwall = Mock()
        mock_powerwall_class.return_value = mock_powerwall
        mock_powerwall.get_reserve.return_value = {"backup_reserve_percentage": 80}
        
        # Mock OAuth manager
        with patch('src.powernight.core.auth.tesla_oauth.TeslaOAuthManager') as mock_oauth:
            mock_oauth.return_value.get_valid_access_token.return_value = "test_token"
            
            connector = PowerwallConnector(email="test@example.com")
            
            # Mock the logger and data parser
            with patch.object(connector, '_log_api_response') as mock_log, \
                 patch.object(connector._data_parser, 'parse_reserve_percentage', return_value=80.0):
                
                connector.connect()
                connector.get_backup_reserve_percentage()
                
                # Verify API response was logged
                mock_log.assert_called()
                # Find the get_backup_reserve_percentage call
                reserve_call = None
                for call in mock_log.call_args_list:
                    if call[0][0] == "get_backup_reserve_percentage":
                        reserve_call = call
                        break
                
                assert reserve_call is not None


if __name__ == "__main__":
    pytest.main([__file__])
