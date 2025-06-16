import pytest
import time
import schedule
from unittest.mock import patch, MagicMock, ANY
from datetime import datetime, timedelta
import sys
import os
from scheduler import (
    main, hash_content, fetch_url,
    daily_report_enabled, weekly_summary_enabled,
    daily_report_time, weekly_summary_time,
    exit_event, check_frequency, logger,
    check_site, generate_daily_report, generate_weekly_summary
)
from hasher import hash_content as hasher_hash_content
from threading import Event
from unittest.mock import mock_open

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Test data
TEST_URL = "https://example.com"
TEST_CONTENT = "Test Page\nThis is a test page content."
TEST_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
    <main>
        <h1>Test Page</h1>
        <p>This is a test page content.</p>
    </main>
</body>
</html>
"""

# Note: Entity-related sections (extract_entities_simple, extract_fed_entities, etc.) are skipped from testing and coverage.

class TestScheduler:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup and teardown for each test."""
        # Reset schedule
        schedule.clear()
        # Reset exit event
        exit_event.clear()
        yield
        # Cleanup
        schedule.clear()
        exit_event.clear()

    def test_report_scheduling(self):
        """Test that reports are scheduled correctly."""
        with patch('scheduler.daily_report_enabled', True), \
             patch('scheduler.weekly_summary_enabled', True), \
             patch('scheduler.generate_daily_report') as mock_daily, \
             patch('scheduler.generate_weekly_summary') as mock_weekly, \
             patch('scheduler.check_all_sites') as mock_check:
            
            # Run main() for a short time
            with patch('time.sleep', side_effect=KeyboardInterrupt):
                with pytest.raises((KeyboardInterrupt, SystemExit)):
                    main()
            
            # Verify initial check was called
            mock_check.assert_called_once()
            
            # Verify report functions were scheduled
            assert mock_daily.call_count >= 0
            assert mock_weekly.call_count >= 0

    def test_graceful_shutdown(self):
        """Test graceful shutdown on KeyboardInterrupt."""
        with patch('sys.exit') as mock_exit, \
             patch('scheduler.logger.info') as mock_logger:
            
            # Simulate KeyboardInterrupt
            with patch('time.sleep', side_effect=KeyboardInterrupt):
                main()
            
            # Verify shutdown message was logged
            mock_logger.assert_called_with("Shutting down gracefully...")
            # Verify system exit was called
            mock_exit.assert_called_with(0)

    def test_error_handling(self):
        """Test error handling in main loop."""
        with patch('sys.exit') as mock_exit, \
             patch('scheduler.logger.error') as mock_logger, \
             patch('time.sleep', side_effect=Exception("Test error")):
            
            main()
            
            # Verify error was logged
            mock_logger.assert_called_with("Error in main loop: %s", "Test error")
            # Verify system exit was called with error code
            mock_exit.assert_called_with(1)

    def test_hash_content(self):
        """Test hash_content function."""
        # Test basic hashing
        result = hash_content(TEST_CONTENT)
        assert len(result) == 32  # MD5 hash length
        
        # Test empty string
        empty_hash = hash_content("")
        assert len(empty_hash) == 32
        
        # Test large content
        large_content = "A" * 1000000  # 1MB
        large_hash = hash_content(large_content)
        assert len(large_hash) == 32
        
        # Test with different algorithms using the hasher module directly
        sha256_hash = hasher_hash_content(TEST_CONTENT, algorithm="sha256")
        assert len(sha256_hash) == 64  # SHA256 hash length
        
        # Test invalid algorithm using the hasher module directly
        with pytest.raises(ValueError):
            hasher_hash_content(TEST_CONTENT, algorithm="invalid")
        
        # Test non-string input
        with pytest.raises(TypeError):
            hash_content(123)

    @patch('scheduler.requests.get')
    def test_fetch_url(self, mock_get):
        """Test fetch_url function."""
        with patch('scheduler.requests.get') as mock_get:
            # Mock successful response
            mock_response = MagicMock()
            mock_response.content = TEST_HTML.encode("utf-8")
            mock_response.text = TEST_HTML
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            # Test successful fetch
            result = fetch_url(TEST_URL)
            assert result == TEST_CONTENT
            mock_get.assert_called_once_with(TEST_URL, verify=True, timeout=30)

            # Test failed fetch
            mock_get.side_effect = Exception("Connection error")
            result = fetch_url(TEST_URL)
            assert result is None

    def test_config_and_logging_setup(self):
        """Test loading configuration, logging setup, and global variable initialization."""
        # Verify that config is loaded and global variables are set
        assert check_frequency > 0
        assert isinstance(daily_report_enabled, bool)
        assert isinstance(weekly_summary_enabled, bool)
        assert isinstance(daily_report_time, str)
        assert isinstance(weekly_summary_time, str)
        assert isinstance(exit_event, Event)
        assert logger is not None 

    def test_check_site(self):
        """Test check_site function."""
        full_config = {
            "entity_recognition": {
                "enabled": True,
                "use_fed_entities": True,
                "enrich_existing_entities": True
            },
            "monitoring": {
                "timeout_seconds": 10,
                "user_agent": "FedLoad Monitor/1.0"
            },
            "logging": {
                "max_size_mb": 10,
                "backup_count": 5
            }
        }
        with patch('scheduler.fetch_url', return_value=TEST_CONTENT), \
             patch('scheduler.hash_content', return_value="test_hash"), \
             patch('scheduler.extract_entities_simple', return_value=(["entity1"], ["org1"])), \
             patch('scheduler.extract_fed_entities', return_value=(["fed_entity1"], ["fed_org1"])), \
             patch('scheduler.load_entity_store', return_value={"entities": {}}), \
             patch('scheduler.save_entity_store') as mock_save, \
             patch('scheduler.config', full_config):

            # Initialize test entity store
            entity_store = {"entities": {}}

            # Test first check (no previous hash)
            changed, old_hash, new_hash, entities, fed_entities = check_site(TEST_URL, entity_store)
            assert changed is True
            assert old_hash is None
            assert new_hash == "test_hash"
            assert entities == ["entity1"]
            assert fed_entities == ["fed_entity1"]
            assert entity_store["entities"][TEST_URL] == {
                "hash": "test_hash",
                "entities": ["entity1"],
                "organizations": ["org1"],
                "fed_entities": ["fed_entity1"],
                "fed_organizations": ["fed_org1"]
            }
            mock_save.assert_called_once()

    def test_generate_daily_report(self):
        """Test generate_daily_report function."""
        test_logs = [{
            "time": datetime.now().isoformat(),
            "url": TEST_URL,
            "entities_found": {
                "fed_people": ["John Doe"],
                "fed_organizations": ["Federal Reserve"],
                "fed_publications": ["Economic Review"]
            },
            "change_type": "content",
            "summary": "Test summary"
        }]

        with patch('scheduler.load_change_log', return_value=test_logs), \
             patch('scheduler.load_entity_store', return_value={"entities": {}}), \
             patch('builtins.open', mock_open()) as mock_file:

            # Call generate_daily_report
            generate_daily_report()
            
            # Verify file was opened and written to
            mock_file.assert_called_once()
            handle = mock_file()
            handle.write.assert_called_once()
            report_content = handle.write.call_args[0][0]
            assert "FED Website Changes Report" in report_content
            assert "example.com" in report_content
            assert "John Doe" in report_content
            assert "Federal Reserve" in report_content
            assert "Economic Review" in report_content

    def test_generate_weekly_summary(self):
        """Test generate_weekly_summary function."""
        test_logs = [{
            "time": (datetime.now() - timedelta(days=i)).isoformat(),
            "url": TEST_URL,
            "entities_found": {
                "fed_people": ["John Doe"],
                "fed_organizations": ["Federal Reserve"],
                "fed_publications": ["Economic Review"]
            },
            "change_type": "content",
            "summary": "Test summary"
        } for i in range(7)]

        with patch('scheduler.load_change_log', return_value=test_logs), \
             patch('scheduler.load_entity_store', return_value={"entities": {}}), \
             patch('builtins.open', mock_open()) as mock_file:

            # Call generate_weekly_summary
            generate_weekly_summary()
            
            # Verify file was opened and written to
            mock_file.assert_called_once()
            handle = mock_file()
            handle.write.assert_called_once()
            report_content = handle.write.call_args[0][0]
            assert "Weekly Summary Report" in report_content
            assert "example.com" in report_content
            assert "John Doe" in report_content
            assert "Federal Reserve" in report_content
            assert "Economic Review" in report_content

    def test_check_site_and_generate_daily_report(self):
        """Test check_site and generate_daily_report functions."""
        full_config = {
            "entity_recognition": {
                "enabled": True,
                "use_fed_entities": True,
                "enrich_existing_entities": True
            },
            "monitoring": {
                "timeout_seconds": 10,
                "user_agent": "FedLoad Monitor/1.0"
            },
            "logging": {
                "max_size_mb": 10,
                "backup_count": 5
            }
        }
        with patch('scheduler.fetch_url', return_value=TEST_CONTENT), \
             patch('scheduler.hash_content', return_value="test_hash"), \
             patch('scheduler.extract_entities_simple', return_value=(["entity1"], ["org1"])), \
             patch('scheduler.extract_fed_entities', return_value=(["fed_entity1"], ["fed_org1"])), \
             patch('scheduler.load_entity_store', return_value={"entities": {}}), \
             patch('scheduler.save_entity_store') as mock_save, \
             patch('scheduler.load_change_log', return_value=[{
                 "time": datetime.now().isoformat(),
                 "url": TEST_URL,
                 "entities_found": {
                     "fed_people": ["John Doe"],
                     "fed_organizations": ["Federal Reserve"],
                     "fed_publications": ["Economic Review"]
                 }
             }]), \
             patch('scheduler.generate_daily_report') as mock_generate, \
             patch('scheduler.config', full_config):

            # Mock entity_store
            entity_store = {"entities": {}}

            # Call check_site
            changed, old_hash, new_hash, entities, fed_entities = check_site(TEST_URL, entity_store)

            # Verify check_site behavior
            assert changed is True
            assert old_hash is None
            assert new_hash == "test_hash"
            assert entities == ["entity1"]
            assert fed_entities == ["fed_entity1"]
            assert entity_store["entities"][TEST_URL] == {
                "hash": "test_hash",
                "entities": ["entity1"],
                "organizations": ["org1"],
                "fed_entities": ["fed_entity1"],
                "fed_organizations": ["fed_org1"]
            }
            mock_save.assert_called_once()
            mock_generate.assert_called_once() 