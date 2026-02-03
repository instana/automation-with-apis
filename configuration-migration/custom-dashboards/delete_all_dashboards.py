#!/usr/bin/env python3
"""Quick script to delete all custom dashboards from target Instana backend."""

import sys
import os
import requests
import urllib3
from pathlib import Path

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import Config

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def delete_all_dashboards(config: Config):
    """Delete all custom dashboards from target backend.
    
    Args:
        config: Configuration object with target backend details
    """
    print("=" * 60)
    print("DELETE ALL DASHBOARDS FROM TARGET")
    print("=" * 60)
    print(f"Target URL: {config.target_url}")
    print()
    
    # Get all dashboards
    print("Fetching all dashboards from target...")
    try:
        response = requests.get(
            f"{config.target_url}/api/custom-dashboard",
            headers=config.get_target_headers(),
            verify=config.verify_ssl
        )
        response.raise_for_status()
        dashboards = response.json()
        print(f"Found {len(dashboards)} dashboards")
    except Exception as e:
        print(f"Error fetching dashboards: {e}")
        return
    
    if not dashboards:
        print("No dashboards to delete.")
        return
    
    # Confirm deletion
    print()
    print("⚠️  WARNING: This will DELETE ALL dashboards from the target system!")
    print()
    for dashboard in dashboards:
        print(f"  - {dashboard.get('title', 'N/A')} (ID: {dashboard.get('id', 'N/A')})")
    print()
    
    confirm = input("Type 'DELETE ALL' to confirm: ")
    if confirm != "DELETE ALL":
        print("Cancelled.")
        return
    
    # Delete dashboards
    print()
    print("Deleting dashboards...")
    deleted_count = 0
    failed_count = 0
    
    for dashboard in dashboards:
        dashboard_id = dashboard.get('id')
        dashboard_title = dashboard.get('title', 'N/A')
        
        if not dashboard_id:
            print(f"✗ Skipping dashboard '{dashboard_title}' - no ID")
            failed_count += 1
            continue
        
        try:
            response = requests.delete(
                f"{config.target_url}/api/custom-dashboard/{dashboard_id}",
                headers=config.get_target_headers(),
                verify=config.verify_ssl
            )
            response.raise_for_status()
            print(f"✓ Deleted dashboard '{dashboard_title}' (ID: {dashboard_id})")
            deleted_count += 1
        except Exception as e:
            print(f"✗ Failed to delete dashboard '{dashboard_title}' (ID: {dashboard_id}): {e}")
            failed_count += 1
    
    print()
    print("=" * 60)
    print(f"Deletion complete: {deleted_count} deleted, {failed_count} failed")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Delete all custom dashboards from target Instana backend"
    )
    parser.add_argument(
        "--config-file",
        default="config.ini",
        help="Path to configuration file (default: config.ini)"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = Config()
    config.load_from_file(args.config_file)
    config.validate()
    
    # Delete all dashboards
    delete_all_dashboards(config)

# Made with Bob
