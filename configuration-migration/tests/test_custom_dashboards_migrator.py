
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

import importlib

# Add the parent directory to the sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'custom-dashboards'))
migrator_module = importlib.import_module("migrator")
CustomDashboardsMigrator = migrator_module.CustomDashboardsMigrator
from config import Config

class TestCustomDashboardsMigrator(unittest.TestCase):

    def setUp(self):
        self.config = Config()
        self.config.source_token = "test"
        self.config.source_url = "http://test.com"
        self.config.target_token = "test"
        self.config.target_url = "http://test.com"
        self.config.on_duplicate = "skip"  # Set default for tests
        self.migrator = CustomDashboardsMigrator(self.config)
        # Force synchronous mode and ensure attributes exist
        self.migrator._use_async = False
        self.migrator.req_custom_dashboards = "/api/custom-dashboard"
        self.migrator.req_shareable_users = "/api/settings/users"

    @patch('requests.get')
    def test_get_source_dashboards(self, mock_get):
        # Mock the first call to get dashboard IDs
        mock_response_ids = MagicMock()
        mock_response_ids.status_code = 200
        mock_response_ids.json.return_value = [{'id': '1', 'title': 'Test Dashboard Summary'}]

        # Mock the second call to get full dashboard details
        mock_response_details = MagicMock()
        mock_response_details.status_code = 200
        mock_response_details.json.return_value = {'id': '1', 'title': 'Test Dashboard', 'widgets': [{'id': 'w1'}]}
        
        mock_get.side_effect = [mock_response_ids, mock_response_details]

        dashboards = self.migrator._get_source_dashboards()
        self.assertEqual(len(dashboards), 1)
        self.assertEqual(dashboards[0]['title'], 'Test Dashboard')
        self.assertIn('widgets', dashboards[0])

    @patch('requests.get')
    def test_get_target_dashboards(self, mock_get):
        # Mock the first call to get dashboard IDs
        mock_response_ids = MagicMock()
        mock_response_ids.status_code = 200
        mock_response_ids.json.return_value = [{'id': '2', 'title': 'Existing Dashboard Summary'}]

        # Mock the second call to get full dashboard details
        mock_response_details = MagicMock()
        mock_response_details.status_code = 200
        mock_response_details.json.return_value = {'id': '2', 'title': 'Existing Dashboard', 'widgets': [{'id': 'w2'}]}
        
        mock_get.side_effect = [mock_response_ids, mock_response_details]

        dashboards = self.migrator._get_target_dashboards()
        self.assertEqual(len(dashboards), 1)
        self.assertEqual(dashboards[0]['title'], 'Existing Dashboard')
        self.assertIn('widgets', dashboards[0])

    @patch('requests.get')
    def test_get_shareable_users(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{'id': 'user1', 'email': 'test@example.com'}]
        mock_get.return_value = mock_response

        users = self.migrator._get_shareable_users(self.config.source_url, self.config.get_source_headers())
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]['email'], 'test@example.com')

    def test_map_users(self):
        source_users = [{'id': 'src_user1', 'email': 'test@example.com'}]
        target_users = [{'id': 'tgt_user1', 'email': 'test@example.com'}]
        user_map = self.migrator._map_users(source_users, target_users)
        self.assertEqual(user_map['src_user1'], 'tgt_user1')

    @patch('requests.post')
    def test_create_dashboard(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'id': 'new_dashboard_id'}
        mock_post.return_value = mock_response

        success = self.migrator._create_dashboard({'title': 'New Dashboard'})
        self.assertTrue(success)

    @patch('requests.put')
    def test_update_dashboard(self, mock_put):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'id': 'updated_dashboard_id'}
        mock_put.return_value = mock_response

        target_dashboards = [{'id': 'dashboard_to_update', 'title': 'Dashboard to Update'}]
        success = self.migrator._update_dashboard({'title': 'Dashboard to Update'}, 'Dashboard to Update', target_dashboards)
        self.assertTrue(success)

    @patch.object(CustomDashboardsMigrator, '_get_source_dashboards')
    @patch.object(CustomDashboardsMigrator, '_get_target_dashboards')
    @patch.object(CustomDashboardsMigrator, '_get_shareable_users')
    @patch.object(CustomDashboardsMigrator, '_map_users')
    def test_migrate_skip_existing(self, mock_map_users, mock_get_users, mock_get_target, mock_get_source):
        mock_get_source.return_value = [{'id': '1', 'title': 'Test Dashboard', 'owner': 'src_user1', 'widgets': [{'id': 'w1', 'width': 1, 'height': 1, 'config': {}}]}]
        mock_get_target.return_value = [{'id': '2', 'title': 'Test Dashboard'}]
        mock_get_users.return_value = [{'id': 'src_user1', 'email': 'test@example.com'}]
        mock_map_users.return_value = {'src_user1': 'tgt_user1'}

        result = self.migrator._migrate_sync()
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(result['migrated'], 0)

if __name__ == '__main__':
    unittest.main()
