"""Unit tests for the CLI module."""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from cli import main


class TestCLI:
    """Test cases for the CLI module."""

    @patch('cli.sys.exit', side_effect=SystemExit(1))
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
        
        with pytest.raises(SystemExit):
            main()
        mock_exit.assert_called_once_with(1)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_events_command(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with events command."""
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
        
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"source": 2, "migrated": 2, "updated": 0, "skipped": 0}
        mock_migrator_cls = MagicMock(return_value=mock_migrator)
        
        with patch.dict('sys.modules', {'migrator': MagicMock(EventsMigrator=mock_migrator_cls)}):
            main()
            mock_exit.assert_called_once_with(0)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_events_command_no_migration(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with events command but no successful migration."""
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
        
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"source": 2, "migrated": 0, "updated": 0, "skipped": 2}
        mock_migrator_cls = MagicMock(return_value=mock_migrator)
        
        with patch.dict('sys.modules', {'migrator': MagicMock(EventsMigrator=mock_migrator_cls)}):
            main()
            mock_exit.assert_called_once_with(1)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_channels_command(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with channels command."""
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
        
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"source": 2, "migrated": 2, "updated": 0, "skipped": 0, "failed": 0}
        mock_migrator_cls = MagicMock(return_value=mock_migrator)
        
        with patch.dict('sys.modules', {'migrator': MagicMock(AlertChannelsMigrator=mock_migrator_cls)}):
            main()
            mock_exit.assert_called_once_with(0)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_channels_command_with_failed(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with channels command when channel migration fails."""
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
        
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"source": 2, "migrated": 1, "updated": 0, "skipped": 0, "failed": 1}
        mock_migrator_cls = MagicMock(return_value=mock_migrator)
        
        with patch.dict('sys.modules', {'migrator': MagicMock(AlertChannelsMigrator=mock_migrator_cls)}):
            main()
            mock_exit.assert_called_once_with(1)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_configs_command(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with configs command."""
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
        
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"migrated": 2, "updated": 0, "skipped": 0}
        mock_migrator_cls = MagicMock(return_value=mock_migrator)
        
        with patch.dict('sys.modules', {'migrator': MagicMock(AlertConfigsMigrator=mock_migrator_cls)}):
            main()
            mock_exit.assert_called_once_with(0)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_configs_command_no_migration(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with configs command but no successful migration."""
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
        
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"migrated": 0, "updated": 0, "skipped": 2}
        mock_migrator_cls = MagicMock(return_value=mock_migrator)
        
        with patch.dict('sys.modules', {'migrator': MagicMock(AlertConfigsMigrator=mock_migrator_cls)}):
            main()
            mock_exit.assert_called_once_with(1)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_events_command_with_update(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with events command that includes updates."""
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
        
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"source": 2, "migrated": 0, "updated": 1, "skipped": 1}
        mock_migrator_cls = MagicMock(return_value=mock_migrator)
        
        with patch.dict('sys.modules', {'migrator': MagicMock(EventsMigrator=mock_migrator_cls)}):
            main()
            mock_exit.assert_called_once_with(0)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_custom_dashboards_command(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with custom-dashboards command."""
        mock_args = type('MockArgs', (), {
            'command': 'custom-dashboards',
            'config_file': 'test_config.ini',
            'source_token': 'test_token',
            'source_url': 'https://test.com',
            'target_token': 'test_token',
            'target_url': 'https://test.com',
            'no_verify_ssl': False,
            'events_source': 'file',
            'events_file_path': 'test.json',
            'default_owner_id': 'user123',
            'on_duplicate': 'skip',
            'max_concurrent': 10,
            'rate_limit': 50,
            'request_timeout': 30,
            'retry_attempts': 3
        })()
        mock_parse_args.return_value = mock_args
        
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"migrated": 3, "updated": 0, "skipped": 0}
        mock_migrator_cls = MagicMock(return_value=mock_migrator)
        
        with patch.dict('sys.modules', {'migrator': MagicMock(CustomDashboardsMigrator=mock_migrator_cls)}):
            main()
            mock_exit.assert_called_once_with(0)

    @patch('cli.sys.exit')
    @patch('cli.Config.from_args')
    @patch('cli.argparse.ArgumentParser.parse_args')
    def test_main_custom_dashboards_no_migration(self, mock_parse_args, mock_config_from_args, mock_exit):
        """Test main function with custom-dashboards command when nothing migrated."""
        mock_args = type('MockArgs', (), {
            'command': 'custom-dashboards',
            'config_file': 'test_config.ini',
            'source_token': 'test_token',
            'source_url': 'https://test.com',
            'target_token': 'test_token',
            'target_url': 'https://test.com',
            'no_verify_ssl': False,
            'events_source': 'file',
            'events_file_path': 'test.json',
            'default_owner_id': 'user123',
            'on_duplicate': 'skip',
            'max_concurrent': 10,
            'rate_limit': 50,
            'request_timeout': 30,
            'retry_attempts': 3
        })()
        mock_parse_args.return_value = mock_args
        
        mock_config = MagicMock()
        mock_config_from_args.return_value = mock_config
        
        mock_migrator = MagicMock()
        mock_migrator.migrate.return_value = {"migrated": 0, "updated": 0, "skipped": 2}
        mock_migrator_cls = MagicMock(return_value=mock_migrator)
        
        with patch.dict('sys.modules', {'migrator': MagicMock(CustomDashboardsMigrator=mock_migrator_cls)}):
            main()
            mock_exit.assert_called_once_with(1)
