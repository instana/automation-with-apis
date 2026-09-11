"""Async optimized version of custom dashboards migrator."""

import copy
import sys
import asyncio
import aiohttp
import json
from typing import Dict, List, Any, Optional

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config
from async_client import AsyncHTTPClient
from rate_limiter import RateLimiter


class CustomDashboardsMigratorAsync:
    """Async version of custom dashboards migrator with performance optimizations."""

    def __init__(self, config: Config):
        """Initialize the async migrator with configuration.
        
        Args:
            config: Configuration object with backend details
        """
        self.config = config
        self.req_custom_dashboards = "/api/custom-dashboard"
        self.req_shareable_users = "/api/settings/users"
        
        # Async infrastructure
        self.semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        self.rate_limiter = RateLimiter(config.rate_limit_per_second)
        self.async_client = AsyncHTTPClient(
            verify_ssl=config.verify_ssl,
            timeout=config.request_timeout,
            max_retries=config.retry_attempts
        )
    
    def migrate(self) -> Dict[str, int]:
        """Synchronous wrapper for async migration (maintains backward compatibility).
        
        Returns:
            Dictionary with counts of source, migrated, updated, and skipped dashboards
        """
        return asyncio.run(self._migrate_async())
    
    async def _migrate_async(self) -> Dict[str, int]:
        """Perform the async migration of custom dashboards.
        
        Returns:
            Dictionary with counts of source, migrated, updated, skipped, and failed dashboards
        """
        # Validate configuration before proceeding
        self.config.validate()
        
        print("Starting migration of custom dashboards...")
        
        # Ask user about override strategy ONCE at the beginning
        override_existing = self._prompt_for_override_strategy()
        
        async with self.async_client as client:
            # Step 1: Get target dashboards first (full detail for equality checks)
            target_dashboards = await self._get_target_dashboards_async(client)
            
            if target_dashboards is None:
                print("Warning: Could not retrieve target dashboards. Duplicate detection disabled.")
                target_dashboards = []
            
            # Build a map of existing dashboard titles to full dicts for duplicate
            # detection and content-equality checks (Bug 3, Bug 9).
            existing_dashboards = {d['title']: d for d in target_dashboards if 'title' in d and 'id' in d}
            print(f"Found {len(existing_dashboards)} existing dashboards in target")

            # The smart-filtering helper uses title-only existence, so pass a
            # compatible title→id map derived from the full dict map.
            existing_ids_by_title = {title: d['id'] for title, d in existing_dashboards.items()}

            # Step 2: Get source dashboards (API or file) with smart filtering
            if self.config.events_source.lower() == "file":
                source_dashboards = self._get_source_dashboards_from_file()
            else:
                source_dashboards = await self._get_source_dashboards_async(client, existing_ids_by_title, override_existing)
            
            if source_dashboards is None:
                return {"source": 0, "migrated": 0, "updated": 0, "skipped": 0, "failed": 0}
            
            # Get users from source and target for mapping
            source_users, target_users = await asyncio.gather(
                self._get_shareable_users_async(client, self.config.source_url, self.config.get_source_headers()),
                self._get_shareable_users_async(client, self.config.target_url, self.config.get_target_headers())
            )
            
            if source_users is None:
                print("Could not retrieve source users, aborting migration.")
                return {"source": 0, "migrated": 0, "updated": 0, "skipped": 0, "failed": 0}
            
            if target_users is None:
                print("Could not retrieve target users, aborting migration.")
                return {"source": len(source_dashboards), "migrated": 0, "updated": 0, "skipped": 0, "failed": 0}
            
            # Map users
            user_map: Dict[str, str] = {}
            if not target_users:
                print("No users found in the target system. All dashboards will be assigned to the default owner ID.")
            else:
                user_map = self._map_users(source_users, target_users)
            
            # Prepare dashboards for migration
            prepared_dashboards = []
            skipped_count = 0
            
            for dashboard in source_dashboards:
                prepared = self._prepare_dashboard(dashboard, user_map)
                if prepared is None:
                    skipped_count += 1
                else:
                    prepared_dashboards.append(prepared)
            
            # Migrate dashboards concurrently, passing existing dashboards map
            results = await self._migrate_dashboards_async(client, prepared_dashboards, override_existing, existing_dashboards)
            
            migrated_count = results.count('created')
            updated_count = results.count('updated')
            skipped_count += results.count('skipped')
            failed_count = results.count('failed')

            print(f"\nMigration complete. Found {len(source_dashboards)} source dashboards, "
                  f"migrated {migrated_count} custom dashboards, updated {updated_count} dashboards, "
                  f"skipped {skipped_count} dashboards, failed {failed_count} dashboards.")
            
            return {
                "source": len(source_dashboards),
                "migrated": migrated_count,
                "updated": updated_count,
                "skipped": skipped_count,
                "failed": failed_count,
            }
    
    def _prompt_for_override_strategy(self) -> bool:
        """Ask user once about override strategy.
        
        Returns:
            True if user wants to override existing dashboards, False otherwise
        """
        # Check config first
        if self.config.on_duplicate == "update":
            print("Configuration set to override existing dashboards")
            return True
        elif self.config.on_duplicate == "skip":
            print("Configuration set to skip existing dashboards")
            return False
        
        # Interactive prompt
        if not sys.stdin.isatty():
            print("Non-interactive mode: Skipping existing dashboards by default")
            return False
        
        print("\n" + "="*60)
        print("DASHBOARD MIGRATION STRATEGY")
        print("="*60)
        print("\nWhat should happen if a dashboard already exists in the target?")
        print("  [o] Override - Replace all existing dashboards with source versions")
        print("  [s] Skip - Keep existing dashboards, only create new ones")
        print("  [c] Cancel - Abort migration")
        print()
        
        while True:
            choice = input("Enter your choice [o/s/c]: ").lower()
            
            if choice in ['o', 'override']:
                print("✓ Will override existing dashboards\n")
                return True
            elif choice in ['s', 'skip']:
                print("✓ Will skip existing dashboards\n")
                return False
            elif choice in ['c', 'cancel']:
                print("Migration cancelled by user")
                return False
            else:
                print("Invalid choice. Please try again.")
    
    def _prepare_dashboard(self, dashboard: Dict[str, Any], user_map: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Prepare a dashboard for migration.

        Returns a deep copy so the original source dict is never mutated.
        
        Args:
            dashboard: Source dashboard
            user_map: Mapping of source user IDs to target user IDs
            target_users: List of users from target system
            
        Returns:
            Prepared dashboard copy or None if should be skipped
        """
        dashboard_title = dashboard.get('title')
        
        if not dashboard_title:
            print("Skipping dashboard with no title")
            return None

        # Work on a copy so the caller's dict is never mutated (Bug 5)
        dashboard = copy.deepcopy(dashboard)

        # Remove the 'owner' field if it exists
        if 'owner' in dashboard:
            del dashboard['owner']
        
        # Remap ownerId to the corresponding target user; fall back to
        # default_owner_id when no mapping exists, and only drop it when
        # neither is available (Bug 2).
        source_owner_id = dashboard.get('ownerId')
        if source_owner_id is not None:
            target_owner_id = user_map.get(source_owner_id, self.config.default_owner_id)
            if target_owner_id:
                dashboard['ownerId'] = target_owner_id
            else:
                del dashboard['ownerId']
        
        # Set accessRules to GLOBAL READ_WRITE with empty relatedId
        # This is the working structure that persists dashboards correctly
        dashboard['accessRules'] = [{
            'accessType': 'READ_WRITE',
            'relationType': 'GLOBAL',
            'relatedId': ''
        }]
        
        # IMPORTANT: Keep the 'id' field from source dashboard
        # The API requires this field to properly create the dashboard
        
        # Ensure widgets are present
        if 'widgets' not in dashboard or not dashboard['widgets']:
            print(f"Warning: Dashboard '{dashboard_title}' has no widgets. Skipping.")
            return None
        
        # Validate widget structure - each widget must have required fields
        for idx, widget in enumerate(dashboard['widgets']):
            missing_fields = []
            if 'id' not in widget or not widget['id']:
                missing_fields.append('id')
            if 'width' not in widget or widget['width'] < 1:
                missing_fields.append('width')
            if 'height' not in widget or widget['height'] < 1:
                missing_fields.append('height')
            if 'config' not in widget:
                missing_fields.append('config')
            
            if missing_fields:
                print(f"Error: Widget {idx} in dashboard '{dashboard_title}' is missing required fields: {', '.join(missing_fields)}")
                print(f"Widget data: {widget}")
                return None
        
        return dashboard

    def _get_source_dashboards_from_file(self) -> Optional[List[Dict[str, Any]]]:
        """Load source dashboards from a local JSON file (Bug 8).

        Args:
            (uses self.config.events_file_path)

        Returns:
            List of dashboard dicts or None if the file cannot be read
        """
        file_path = self.config.events_file_path
        print(f"Loading source dashboards from file: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except FileNotFoundError:
            print(f"Error: Source file not found: {file_path}")
            return None
        except json.JSONDecodeError as exc:
            print(f"Error: Could not parse JSON from {file_path}: {exc}")
            return None

        if not isinstance(data, list):
            print(f"Error: Expected a JSON array in {file_path}, got {type(data).__name__}")
            return None

        print(f"Loaded {len(data)} dashboards from file")
        return data

    async def _get_source_dashboards_async(self, client: AsyncHTTPClient, existing_dashboards: Dict[str, str], override_existing: bool) -> Optional[List[Dict[str, Any]]]:
        """Get custom dashboards from source backend with smart filtering.
        
        Args:
            client: Async HTTP client
            existing_dashboards: Map of existing dashboard titles to IDs in target
            override_existing: Whether to override existing dashboards
            
        Returns:
            List of custom dashboards or None if failed
        """
        try:
            print("Fetching custom dashboard list from source API...")
            async with client.retry_client.get(
                f"{self.config.source_url}{self.req_custom_dashboards}",
                headers=self.config.get_source_headers()
            ) as response:
                response.raise_for_status()
                dashboard_summaries = await response.json()
            
            print(f"Found {len(dashboard_summaries)} dashboards in source")
            
            # Smart filtering based on override_existing flag
            if not override_existing and existing_dashboards:
                # Filter out dashboards that already exist in target (skip mode)
                dashboards_to_fetch = [
                    d for d in dashboard_summaries
                    if d.get('title') not in existing_dashboards
                ]
                skipped_count = len(dashboard_summaries) - len(dashboards_to_fetch)
                if skipped_count > 0:
                    print(f"⚡ Smart filtering: Skipping {skipped_count} existing dashboards (will not fetch details)")
                    print(f"   Only fetching details for {len(dashboards_to_fetch)} new dashboards")
            else:
                # Fetch all dashboards (update mode or no existing dashboards)
                dashboards_to_fetch = dashboard_summaries
                if override_existing and existing_dashboards:
                    print(f"   Fetching all {len(dashboards_to_fetch)} dashboards (update mode)")
            
            if not dashboards_to_fetch:
                print("No dashboards to migrate")
                return []
            
            dashboard_ids = [d['id'] for d in dashboards_to_fetch]
            print(f"Fetching details for {len(dashboard_ids)} dashboards concurrently...")
            
            # Fetch dashboard details concurrently
            tasks = [
                self._fetch_dashboard_detail(client, dashboard_id, 'source')
                for dashboard_id in dashboard_ids
            ]
            
            full_dashboards = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions and log errors
            successful_dashboards = []
            for i, result in enumerate(full_dashboards):
                if isinstance(result, Exception):
                    print(f"Warning: Failed to fetch dashboard {dashboard_ids[i]}: {result}")
                else:
                    successful_dashboards.append(result)
            
            print(f"Successfully fetched {len(successful_dashboards)} dashboards from source")
            return successful_dashboards
            
        except Exception as e:
            print(f"Error retrieving source dashboards: {e}")
            return None
    
    async def _fetch_dashboard_detail(self, client: AsyncHTTPClient, dashboard_id: str, backend: str) -> Dict[str, Any]:
        """Fetch single dashboard detail with rate limiting and semaphore.
        
        Args:
            client: Async HTTP client
            dashboard_id: Dashboard ID to fetch
            backend: 'source' or 'target'
            
        Returns:
            Dashboard details
        """
        async with self.semaphore:
            await self.rate_limiter.acquire()
            
            url = self.config.source_url if backend == 'source' else self.config.target_url
            headers = self.config.get_source_headers() if backend == 'source' else self.config.get_target_headers()
            
            async with client.retry_client.get(
                f"{url}{self.req_custom_dashboards}/{dashboard_id}",
                headers=headers
            ) as response:
                response.raise_for_status()
                return await response.json()
    
    async def _get_target_dashboards_async(self, client: AsyncHTTPClient) -> Optional[List[Dict[str, Any]]]:
        """Get all custom dashboards from target backend (full detail).

        The list endpoint returns summary objects only.  Full details are
        fetched individually so that content-equality comparisons work
        correctly (Bug 3).
        
        Args:
            client: Async HTTP client
            
        Returns:
            List of full dashboards or None on error
        """
        try:
            async with client.retry_client.get(
                f"{self.config.target_url}{self.req_custom_dashboards}",
                headers=self.config.get_target_headers()
            ) as response:
                response.raise_for_status()
                summaries = await response.json()

            print(f"Retrieved {len(summaries)} dashboard summaries from target; fetching full details…")

            dashboard_ids = [d['id'] for d in summaries if 'id' in d]
            tasks = [
                self._fetch_dashboard_detail(client, dashboard_id, 'target')
                for dashboard_id in dashboard_ids
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            full_dashboards = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"Warning: Failed to fetch target dashboard {dashboard_ids[i]}: {result}")
                else:
                    full_dashboards.append(result)

            print(f"Fetched {len(full_dashboards)} full target dashboards")
            return full_dashboards
        except Exception as e:
            print(f"Error retrieving target dashboards: {e}")
            return None
    
    async def _get_shareable_users_async(self, client: AsyncHTTPClient, base_url: str, headers: Dict[str, str]) -> Optional[List[Dict[str, Any]]]:
        """Get all shareable users from a backend.
        
        Args:
            client: Async HTTP client
            base_url: Base URL of the backend
            headers: Headers for authentication
            
        Returns:
            List of shareable users or None if failed
        """
        try:
            async with client.retry_client.get(
                f"{base_url}{self.req_shareable_users}",
                headers=headers
            ) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            print(f"Error retrieving shareable users: {e}")
            return None
    
    def _map_users(self, source_users: List[Dict[str, Any]], target_users: List[Dict[str, Any]]) -> Dict[str, str]:
        """Map users between source and target backends based on email.
        
        Args:
            source_users: List of users from the source backend
            target_users: List of users from the target backend
            
        Returns:
            A dictionary mapping source user IDs to target user IDs
        """
        user_map: Dict[str, str] = {}
        if not source_users or not target_users:
            return user_map
        
        target_user_emails = {user['email']: user['id'] for user in target_users if 'email' in user and 'id' in user}
        
        for source_user in source_users:
            if 'email' in source_user and 'id' in source_user:
                source_email = source_user.get('email')
                if source_email in target_user_emails:
                    user_map[source_user['id']] = target_user_emails[source_email]
        
        return user_map
    
    async def _migrate_dashboards_async(self, client: AsyncHTTPClient, dashboards: List[Dict[str, Any]], override_existing: bool, existing_dashboards: Dict[str, str]) -> List[str]:
        """Migrate dashboards concurrently.
        
        Args:
            client: Async HTTP client
            dashboards: List of prepared dashboards
            override_existing: Whether to override existing dashboards
            existing_dashboards: Map of dashboard titles to full dashboard dicts in target
            
        Returns:
            List of results ('created', 'updated', 'skipped', or 'failed')
        """
        # Migrations are run sequentially, not concurrently.
        # Firing all POSTs simultaneously overwhelms the Instana backend:
        # it accepts every request and hands back IDs, but the writes race
        # each other internally and some records end up with null fields that
        # are invisible in the UI even though a GET returns them.
        # Sequential execution gives the backend time to fully commit each
        # write before the next one arrives.
        results = []
        for dashboard in dashboards:
            try:
                result = await self._create_or_update_dashboard_async(
                    client, dashboard, override_existing, existing_dashboards
                )
                results.append(result)
            except Exception:
                results.append('failed')
        return results
    
    async def _create_or_update_dashboard_async(self, client: AsyncHTTPClient, dashboard: Dict[str, Any], override_existing: bool, existing_dashboards: Dict[str, Any]) -> str:
        """Create dashboard, or update if it exists and override is enabled.

        existing_dashboards maps title → full target dashboard dict so that
        a content-equality check (Bug 9) can be performed without an extra
        network round-trip.
        
        Args:
            client: Async HTTP client
            dashboard: Dashboard configuration
            override_existing: Whether to override existing dashboards
            existing_dashboards: Map of dashboard titles to full target dashboard dicts
            
        Returns:
            'created', 'updated', 'skipped', or 'failed'
        """
        dashboard_title = dashboard.get('title', 'N/A')
        
        # Check if dashboard already exists
        if dashboard_title in existing_dashboards:
            existing_dashboard = existing_dashboards[dashboard_title]
            existing_id = existing_dashboard['id']
            if override_existing:
                # Content-equality check: skip the PUT when nothing changed (Bug 9)
                source_widgets = dashboard.get('widgets')
                target_widgets = existing_dashboard.get('widgets')
                if source_widgets == target_widgets:
                    print(f"= Dashboard '{dashboard_title}' is identical to target, skipping update...")
                    return 'skipped'
                print(f"⟳ Dashboard '{dashboard_title}' already exists (ID: {existing_id}), updating...")
                return await self._update_existing_dashboard_async(client, dashboard, dashboard_title, existing_id)
            else:
                print(f"⊘ Dashboard '{dashboard_title}' already exists (ID: {existing_id}), skipping...")
                return 'skipped'
        
        async with self.semaphore:
            await self.rate_limiter.acquire()
            
            try:
                # Try to create
                async with client.retry_client.post(
                    f"{self.config.target_url}{self.req_custom_dashboards}",
                    headers=self.config.get_target_headers(),
                    json=dashboard
                ) as response:
                    response.raise_for_status()
                    new_dashboard = await response.json()
                    
                    if 'id' in new_dashboard:
                        print(f"✓ Created dashboard '{dashboard_title}' (ID: {new_dashboard['id']})")
                        return 'created'
                    else:
                        print(f"✗ Failed to create dashboard '{dashboard_title}' - no ID returned")
                        return 'failed'
                        
            except aiohttp.ClientResponseError as e:
                # Check if it's a conflict (dashboard already exists)
                if e.status == 409:
                    if override_existing:
                        # Try to find and update existing dashboard
                        existing_id = await self._find_dashboard_id_by_title_async(client, dashboard_title)
                        if existing_id:
                            return await self._update_existing_dashboard_async(client, dashboard, dashboard_title, existing_id)
                        else:
                            print(f"⚠ Dashboard '{dashboard_title}' exists but couldn't get ID for update")
                            return 'skipped'
                    else:
                        print(f"⊘ Skipped dashboard '{dashboard_title}' - already exists")
                        return 'skipped'
                else:
                    print(f"✗ Failed to create dashboard '{dashboard_title}': {e}")
                    return 'failed'
            except Exception as e:
                print(f"✗ Failed to create dashboard '{dashboard_title}': {e}")
                return 'failed'
    
    async def _find_dashboard_id_by_title_async(self, client: AsyncHTTPClient, title: str) -> Optional[str]:
        """Find dashboard ID by title (only called on conflict).
        
        Args:
            client: Async HTTP client
            title: Dashboard title to search for
            
        Returns:
            Dashboard ID or None if not found
        """
        try:
            async with client.retry_client.get(
                f"{self.config.target_url}{self.req_custom_dashboards}",
                headers=self.config.get_target_headers()
            ) as response:
                response.raise_for_status()
                dashboards = await response.json()
                
                for d in dashboards:
                    if d.get('title') == title and 'id' in d:
                        return d['id']
                return None
        except Exception as e:
            print(f"⚠ Could not look up dashboard ID for '{title}': {e}")
            return None
    
    async def _update_existing_dashboard_async(self, client: AsyncHTTPClient, dashboard: Dict[str, Any], title: str, dashboard_id: str) -> str:
        """Update an existing dashboard.
        
        Args:
            client: Async HTTP client
            dashboard: Dashboard configuration
            title: Dashboard title for logging
            dashboard_id: ID of dashboard to update
            
        Returns:
            'updated' or 'skipped'
        """
        try:
            if 'id' in dashboard:
                del dashboard['id']
            
            async with client.retry_client.put(
                f"{self.config.target_url}{self.req_custom_dashboards}/{dashboard_id}",
                headers=self.config.get_target_headers(),
                json=dashboard
            ) as response:
                response.raise_for_status()
                print(f"↻ Updated dashboard '{title}' (ID: {dashboard_id})")
                return 'updated'
        except Exception as e:
            print(f"✗ Failed to update dashboard '{title}': {e}")
            return 'skipped'

