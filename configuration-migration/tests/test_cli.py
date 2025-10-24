"""Unit tests for the CLI module."""

import pytest
import sys
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from cli import main


class TestCLI:
    """Test cases for the CLI module."""

    @patch('cli.sys.exit')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_no_command(self, mock_parse_args, mock_exit):
        """Test main function when no command is provided."""
        # Mock parsed args with no command
        mock_args = type('MockArgs', (), {
            'command': None,
            'config_file': None,
            'source_token': None,
            'source_url': None,
            'target_token': None,
            'target_url': None,
            'no_verify_ssl': False,
            'events_source': None,
            'events_file_path': None
        })()
        mock_parse_args.return_value = mock_args
        
        # Mock the help method
        mock_parser = MagicMock()
        with patch('cli.argparse.ArgumentParser', return_value=mock_parser):
            main()
            
            mock_exit.assert_called_once_with(1)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_events_command(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with events command."""
        # Mock parsed args with events command
        mock_args = type('MockArgs', (), {
            'command': 'events',
            'config_file': 'test_config.ini',
            'source_token': 'test_token',
            'source_url': 'https://test.com',
            'target_token': 'test_token',
            'target_url': 'https://test.com',
            'no_verify_ssl': False,
            'events_source': 'file',
            'events_file_path': 'test.json'
        })()
        mock_parse_args.return_value = mock_args
        
        # Mock config
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        # Mock EventsMigrator
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"source": 2, "migrated": 2, "updated": 0, "skipped": 0}
        
        with patch('cli.EventsMigrator', return_value=mock_migrator):
            main()
            
            # Should exit with success (0) since migrated > 0
            mock_exit.assert_called_once_with(0)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_events_command_no_migration(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with events command but no successful migration."""
        # Mock parsed args with events command
        mock_args = type('MockArgs', (), {
            'command': 'events',
            'config_file': 'test_config.ini',
            'source_token': 'test_token',
            'source_url': 'https://test.com',
            'target_token': 'test_token',
            'target_url': 'https://test.com',
            'no_verify_ssl': False,
            'events_source': 'file',
            'events_file_path': 'test.json'
        })()
        mock_parse_args.return_value = mock_args
        
        # Mock config
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        # Mock EventsMigrator with no successful migration
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"source": 2, "migrated": 0, "updated": 0, "skipped": 2}
        
        with patch('cli.EventsMigrator', return_value=mock_migrator):
            main()
            
            # Should exit with error (1) since migrated = 0
            mock_exit.assert_called_once_with(1)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_channels_command(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with channels command."""
        # Mock parsed args with channels command
        mock_args = type('MockArgs', (), {
            'command': 'channels',
            'config_file': 'test_config.ini',
            'source_token': 'test_token',
            'source_url': 'https://test.com',
            'target_token': 'test_token',
            'target_url': 'https://test.com',
            'no_verify_ssl': False,
            'events_source': 'file',
            'events_file_path': 'test.json'
        })()
        mock_parse_args.return_value = mock_args
        
        # Mock config
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        # Mock AlertChannelsMigrator
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"source": 2, "migrated": 2, "updated": 0, "skipped": 0}
        
        with patch('cli.AlertChannelsMigrator', return_value=mock_migrator):
            main()
            
            # Should exit with success (0) since migrated > 0
            mock_exit.assert_called_once_with(0)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_configs_command(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with configs command."""
        # Mock parsed args with configs command
        mock_args = type('MockArgs', (), {
            'command': 'configs',
            'config_file': 'test_config.ini',
            'source_token': 'test_token',
            'source_url': 'https://test.com',
            'target_token': 'test_token',
            'target_url': 'https://test.com',
            'no_verify_ssl': False,
            'events_source': 'file',
            'events_file_path': 'test.json'
        })()
        mock_parse_args.return_value = mock_args
        
        # Mock config
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        # Mock AlertConfigsMigrator
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"migrated": 2, "updated": 0, "skipped": 0}
        
        with patch('cli.AlertConfigsMigrator', return_value=mock_migrator):
            main()
            
            # Should exit with success (0) since migrated > 0
            mock_exit.assert_called_once_with(0)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_configs_command_no_migration(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with configs command but no successful migration."""
        # Mock parsed args with configs command
        mock_args = type('MockArgs', (), {
            'command': 'configs',
            'config_file': 'test_config.ini',
            'source_token': 'test_token',
            'source_url': 'https://test.com',
            'target_token': 'test_token',
            'target_url': 'https://test.com',
            'no_verify_ssl': False,
            'events_source': 'file',
            'events_file_path': 'test.json'
        })()
        mock_parse_args.return_value = mock_args
        
        # Mock config
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        # Mock AlertConfigsMigrator with no successful migration
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"migrated": 0, "updated": 0, "skipped": 2}
        
        with patch('cli.AlertConfigsMigrator', return_value=mock_migrator):
            main()
            
            # Should exit with error (1) since migrated = 0
            mock_exit.assert_called_once_with(1)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_events_command_with_update(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with events command that includes updates."""
        # Mock parsed args with events command
        mock_args = type('MockArgs', (), {
            'command': 'events',
            'config_file': 'test_config.ini',
            'source_token': 'test_token',
            'source_url': 'https://test.com',
            'target_token': 'test_token',
            'target_url': 'https://test.com',
            'no_verify_ssl': False,
            'events_source': 'file',
            'events_file_path': 'test.json'
        })()
        mock_parse_args.return_value = mock_args
        
        # Mock config
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        # Mock EventsMigrator with updates
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"source": 2, "migrated": 0, "updated": 1, "skipped": 1}
        
        with patch('cli.EventsMigrator', return_value=mock_migrator):
            main()
            
            # Should exit with success (0) since updated > 0
            mock_exit.assert_called_once_with(0)
