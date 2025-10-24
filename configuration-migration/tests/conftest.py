"""Shared test fixtures and configuration."""

import pytest
import sys
import os
from unittest.mock import MagicMock

# Add the parent directory to the path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def sample_config():
    """Provide a sample configuration for testing."""
    config = MagicMock()
    config.source_token = "test_source_token"
    config.source_url = "https://test-source.com"
    config.target_token = "test_target_token"
    config.target_url = "https://test-target.com"
    config.verify_ssl = True
    config.events_source = "file"
    config.events_file_path = "test_events.json"
    
    # Mock the header methods
    config.get_source_headers.return_value = {
        "Authorization": "apiToken test_source_token",
        "Content-Type": "application/json"
    }
    config.get_target_headers.return_value = {
        "Authorization": "apiToken test_target_token",
        "Content-Type": "application/json"
    }
    
    return config


@pytest.fixture
def sample_events():
    """Provide sample events data for testing."""
    return [
        {
            "name": "Test Event 1",
            "query": "entity.type == 'service'",
            "description": "Test event description"
        },
        {
            "name": "Test Event 2",
            "query": "entity.type == 'host'",
            "description": "Another test event"
        }
    ]


@pytest.fixture
def sample_channels():
    """Provide sample alert channels data for testing."""
    return [
        {
            "name": "Email Channel",
            "type": "email",
            "email": "test@example.com"
        },
        {
            "name": "Slack Channel",
            "type": "slack",
            "webhookUrl": "https://hooks.slack.com/test"
        }
    ]


@pytest.fixture
def sample_alert_configs():
    """Provide sample alert configurations data for testing."""
    return [
        {
            "alertName": "High CPU Alert",
            "eventFilteringConfiguration": {
                "query": "entity.type == 'service'",
                "ruleIds": [],
                "eventTypes": []
            }
        },
        {
            "alertName": "Memory Alert",
            "eventFilteringConfiguration": {
                "query": "entity.type == 'host'",
                "ruleIds": [],
                "eventTypes": []
            }
        }
    ]
