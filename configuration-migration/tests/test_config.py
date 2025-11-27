"""Unit tests for the Config class."""

import pytest
import tempfile
import os
from unittest.mock import patch, mock_open
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config


class TestConfig:
    """Test cases for the Config class."""

    def test_init_default_values(self):
        """Test that Config initializes with correct default values."""
        config = Config()
        
        assert config.source_token == ""
        assert config.source_url == ""
        assert config.target_token == ""
        assert config.target_url == ""
        assert config.verify_ssl is True
        assert config.events_source == "api"
        assert config.events_file_path == "source_events.json"

    def test_load_from_file(self):
        """Test loading configuration from a file."""
        config_content = """
[source]
token = test_source_token
url = https://source.example.com

[target]
token = test_target_token
url = https://target.example.com

[general]
verify_ssl = false
events_source = file
events_file_path = test_events.json
"""
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(config_content)
            temp_file = f.name
        
        try:
            config = Config()
            config.load_from_file(temp_file)
            
            assert config.source_token == "test_source_token"
            assert config.source_url == "https://source.example.com"
            assert config.target_token == "test_target_token"
            assert config.target_url == "https://target.example.com"
            assert config.verify_ssl is False
            assert config.events_source == "file"
            assert config.events_file_path == "test_events.json"
        finally:
            os.unlink(temp_file)

    @patch.dict(os.environ, {
        'EVENTS_MIGRATOR_SOURCE_TOKEN': 'env_source_token',
        'EVENTS_MIGRATOR_SOURCE_URL': 'https://env.source.com',
        'EVENTS_MIGRATOR_TARGET_TOKEN': 'env_target_token',
        'EVENTS_MIGRATOR_TARGET_URL': 'https://env.target.com',
        'EVENTS_MIGRATOR_VERIFY_SSL': 'false',
        'EVENTS_MIGRATOR_EVENTS_SOURCE': 'file',
        'EVENTS_MIGRATOR_EVENTS_FILE_PATH': 'env_events.json'
    })
    def test_load_from_env(self):
        """Test loading configuration from environment variables."""
        config = Config()
        config.load_from_env()
        
        assert config.source_token == "env_source_token"
        assert config.source_url == "https://env.source.com"
        assert config.target_token == "env_target_token"
        assert config.target_url == "https://env.target.com"
        assert config.verify_ssl is False
        assert config.events_source == "file"
        assert config.events_file_path == "env_events.json"

    def test_get_source_headers(self):
        """Test getting source headers."""
        config = Config()
        config.source_token = "test_token"
        
        headers = config.get_source_headers()
        
        assert headers == {
            "Authorization": "apiToken test_token",
            "Content-Type": "application/json"
        }

    def test_get_target_headers(self):
        """Test getting target headers."""
        config = Config()
        config.target_token = "test_token"
        
        headers = config.get_target_headers()
        
        assert headers == {
            "Authorization": "apiToken test_token",
            "Content-Type": "application/json"
        }

    def test_validate_success(self):
        """Test successful validation with all required fields."""
        config = Config()
        config.source_token = "source_token"
        config.source_url = "https://source.com"
        config.target_token = "target_token"
        config.target_url = "https://target.com"
        
        # Should not raise any exception
        config.validate()

    def test_validate_missing_source_token(self):
        """Test validation fails when source token is missing."""
        config = Config()
        config.source_url = "https://source.com"
        config.target_token = "target_token"
        config.target_url = "https://target.com"
        
        with pytest.raises(ValueError, match="Source API token is required"):
            config.validate()

    def test_validate_missing_source_url(self):
        """Test validation fails when source URL is missing."""
        config = Config()
        config.source_token = "source_token"
        config.target_token = "target_token"
        config.target_url = "https://target.com"
        
        with pytest.raises(ValueError, match="Source backend URL is required"):
            config.validate()

    def test_validate_missing_target_token(self):
        """Test validation fails when target token is missing."""
        config = Config()
        config.source_token = "source_token"
        config.source_url = "https://source.com"
        config.target_url = "https://target.com"
        
        with pytest.raises(ValueError, match="Target API token is required"):
            config.validate()

    def test_validate_missing_target_url(self):
        """Test validation fails when target URL is missing."""
        config = Config()
        config.source_token = "source_token"
        config.source_url = "https://source.com"
        config.target_token = "target_token"
        
        with pytest.raises(ValueError, match="Target backend URL is required"):
            config.validate()

    @patch('config.argparse.ArgumentParser.parse_args')
    def test_from_args_with_config_file(self, mock_parse_args):
        """Test creating config from args with config file."""
        # Mock parsed args
        mock_args = type('MockArgs', (), {
            'config_file': 'test_config.ini',
            'source_token': None,
            'source_url': None,
            'target_token': None,
            'target_url': None,
            'no_verify_ssl': False,
            'events_source': None,
            'events_file_path': None
        })()
        mock_parse_args.return_value = mock_args
        
        config_content = """
[source]
token = file_source_token
url = https://file.source.com

[target]
token = file_target_token
url = https://file.target.com
"""
        
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=config_content)):
                config = Config.from_args()
                
                assert config.source_token == "file_source_token"
                assert config.source_url == "https://file.source.com"
                assert config.target_token == "file_target_token"
                assert config.target_url == "https://file.target.com"

    @patch('config.argparse.ArgumentParser.parse_args')
    def test_from_args_command_line_override(self, mock_parse_args):
        """Test that command line args override config file."""
        # Mock parsed args
        mock_args = type('MockArgs', (), {
            'config_file': 'test_config.ini',
            'source_token': 'cli_source_token',
            'source_url': 'https://cli.source.com',
            'target_token': 'cli_target_token',
            'target_url': 'https://cli.target.com',
            'no_verify_ssl': True,
            'events_source': 'file',
            'events_file_path': 'cli_events.json'
        })()
        mock_parse_args.return_value = mock_args
        
        config_content = """
[source]
token = file_source_token
url = https://file.source.com

[target]
token = file_target_token
url = https://file.target.com
"""
        
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=config_content)):
                config = Config.from_args()
                
                # Command line args should override config file
                assert config.source_token == "cli_source_token"
                assert config.source_url == "https://cli.source.com"
                assert config.target_token == "cli_target_token"
                assert config.target_url == "https://cli.target.com"
                assert config.verify_ssl is False
                assert config.events_source == "file"
                assert config.events_file_path == "cli_events.json"
