"""Configuration handling for Custom Events Migrator."""

import os
import argparse
import configparser
from typing import Dict, Optional


class Config:
    """Configuration handler for Custom Events Migrator."""

    def __init__(self):
        """Initialize configuration with default values."""
        self.source_token = ""
        self.source_url = ""
        self.target_token = ""
        self.target_url = ""
        self.verify_ssl = True
        self.events_source = "api"  # Default to API source
        self.events_file_path = "source_events.json"  # Default file path
        self.default_owner_id = None # Default owner ID for unmapped users
        self.on_duplicate = "ask" # Default action for duplicate items
        
        # Performance tuning parameters
        self.max_concurrent_requests = 10  # Maximum concurrent API requests
        self.rate_limit_per_second = 50    # API requests per second limit
        self.request_timeout = 30          # Timeout per request in seconds
        self.retry_attempts = 3            # Number of retry attempts for failed requests

    @classmethod
    def from_args(cls, args: Optional[list] = None) -> 'Config':
        """Create configuration from command line arguments.
        
        Args:
            args: Command line arguments (uses sys.argv if None)
            
        Returns:
            Config object with values from command line arguments
        """
        parser = argparse.ArgumentParser(
            description="Migrate custom events between Instana backends"
        )
        
        parser.add_argument(
            "--source-token", 
            help="API token for source backend"
        )
        parser.add_argument(
            "--source-url", 
            help="URL for source backend"
        )
        parser.add_argument(
            "--target-token", 
            help="API token for target backend"
        )
        parser.add_argument(
            "--target-url", 
            help="URL for target backend"
        )
        parser.add_argument(
            "--config-file",
            help="Path to configuration file"
        )
        parser.add_argument(
            "--no-verify-ssl",
            action="store_true",
            help="Disable SSL certificate verification"
        )
        parser.add_argument(
            "--events-source",
            choices=["api", "file"],
            help="Source for custom events (api or file)"
        )
        parser.add_argument(
            "--events-file-path",
            help="Path to the source events JSON file (when using file source)"
        )
        parser.add_argument(
            "--default-owner-id",
            help="Default owner ID for unmapped users"
        )
        parser.add_argument(
            "--on-duplicate",
            choices=["skip", "update", "cancel"],
            help="Action to take when a duplicate is found (default: ask)"
        )
        parser.add_argument(
            "--max-concurrent",
            type=int,
            help="Maximum concurrent API requests (default: 10)"
        )
        parser.add_argument(
            "--rate-limit",
            type=int,
            help="API requests per second limit (default: 50)"
        )
        parser.add_argument(
            "--request-timeout",
            type=int,
            help="Timeout per request in seconds (default: 30)"
        )
        parser.add_argument(
            "--retry-attempts",
            type=int,
            help="Number of retry attempts for failed requests (default: 3)"
        )
        
        parsed_args = parser.parse_args(args)
        
        config = cls()
        
        # Load from config file if specified
        if parsed_args.config_file:
            config.load_from_file(parsed_args.config_file)
        
        # Command line arguments override config file
        if parsed_args.source_token:
            config.source_token = parsed_args.source_token
        if parsed_args.source_url:
            config.source_url = parsed_args.source_url
        if parsed_args.target_token:
            config.target_token = parsed_args.target_token
        if parsed_args.target_url:
            config.target_url = parsed_args.target_url
        if parsed_args.no_verify_ssl:
            config.verify_ssl = False
        if parsed_args.events_source:
            config.events_source = parsed_args.events_source
        if parsed_args.events_file_path:
            config.events_file_path = parsed_args.events_file_path
        if parsed_args.default_owner_id:
            config.default_owner_id = parsed_args.default_owner_id
        if parsed_args.on_duplicate:
            config.on_duplicate = parsed_args.on_duplicate
        if parsed_args.max_concurrent:
            config.max_concurrent_requests = parsed_args.max_concurrent
        if parsed_args.rate_limit:
            config.rate_limit_per_second = parsed_args.rate_limit
        if parsed_args.request_timeout:
            config.request_timeout = parsed_args.request_timeout
        if parsed_args.retry_attempts:
            config.retry_attempts = parsed_args.retry_attempts
            
        # Environment variables override command line arguments
        config.load_from_env()
        
        return config
    
    def load_from_file(self, file_path: str) -> None:
        """Load configuration from a file.
        
        Args:
            file_path: Path to the configuration file
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
            
        parser = configparser.ConfigParser()
        parser.read(file_path)
        
        if "source" in parser:
            if "token" in parser["source"]:
                self.source_token = parser["source"]["token"]
            if "url" in parser["source"]:
                self.source_url = parser["source"]["url"]
                
        if "target" in parser:
            if "token" in parser["target"]:
                self.target_token = parser["target"]["token"]
            if "url" in parser["target"]:
                self.target_url = parser["target"]["url"]
                
        if "general" in parser:
            if "verify_ssl" in parser["general"]:
                self.verify_ssl = parser["general"].getboolean("verify_ssl")
            if "events_source" in parser["general"]:
                self.events_source = parser["general"]["events_source"]
            if "events_file_path" in parser["general"]:
                self.events_file_path = parser["general"]["events_file_path"]
            if "default_owner_id" in parser["general"]:
                self.default_owner_id = parser["general"]["default_owner_id"]
            if "on_duplicate" in parser["general"]:
                self.on_duplicate = parser["general"]["on_duplicate"]
            if "max_concurrent_requests" in parser["general"]:
                self.max_concurrent_requests = parser["general"].getint("max_concurrent_requests")
            if "rate_limit_per_second" in parser["general"]:
                self.rate_limit_per_second = parser["general"].getint("rate_limit_per_second")
            if "request_timeout" in parser["general"]:
                self.request_timeout = parser["general"].getint("request_timeout")
            if "retry_attempts" in parser["general"]:
                self.retry_attempts = parser["general"].getint("retry_attempts")
    
    def load_from_env(self) -> None:
        """Load configuration from environment variables."""
        if "EVENTS_MIGRATOR_SOURCE_TOKEN" in os.environ:
            self.source_token = os.environ["EVENTS_MIGRATOR_SOURCE_TOKEN"]
        if "EVENTS_MIGRATOR_SOURCE_URL" in os.environ:
            self.source_url = os.environ["EVENTS_MIGRATOR_SOURCE_URL"]
        if "EVENTS_MIGRATOR_TARGET_TOKEN" in os.environ:
            self.target_token = os.environ["EVENTS_MIGRATOR_TARGET_TOKEN"]
        if "EVENTS_MIGRATOR_TARGET_URL" in os.environ:
            self.target_url = os.environ["EVENTS_MIGRATOR_TARGET_URL"]
        if "EVENTS_MIGRATOR_VERIFY_SSL" in os.environ:
            self.verify_ssl = os.environ["EVENTS_MIGRATOR_VERIFY_SSL"].lower() != "false"
        if "EVENTS_MIGRATOR_EVENTS_SOURCE" in os.environ:
            self.events_source = os.environ["EVENTS_MIGRATOR_EVENTS_SOURCE"]
        if "EVENTS_MIGRATOR_EVENTS_FILE_PATH" in os.environ:
            self.events_file_path = os.environ["EVENTS_MIGRATOR_EVENTS_FILE_PATH"]
        if "EVENTS_MIGRATOR_DEFAULT_OWNER_ID" in os.environ:
            self.default_owner_id = os.environ["EVENTS_MIGRATOR_DEFAULT_OWNER_ID"]
        if "EVENTS_MIGRATOR_ON_DUPLICATE" in os.environ:
            self.on_duplicate = os.environ["EVENTS_MIGRATOR_ON_DUPLICATE"]
        if "EVENTS_MIGRATOR_MAX_CONCURRENT" in os.environ:
            self.max_concurrent_requests = int(os.environ["EVENTS_MIGRATOR_MAX_CONCURRENT"])
        if "EVENTS_MIGRATOR_RATE_LIMIT" in os.environ:
            self.rate_limit_per_second = int(os.environ["EVENTS_MIGRATOR_RATE_LIMIT"])
        if "EVENTS_MIGRATOR_REQUEST_TIMEOUT" in os.environ:
            self.request_timeout = int(os.environ["EVENTS_MIGRATOR_REQUEST_TIMEOUT"])
        if "EVENTS_MIGRATOR_RETRY_ATTEMPTS" in os.environ:
            self.retry_attempts = int(os.environ["EVENTS_MIGRATOR_RETRY_ATTEMPTS"])
    
    def validate(self) -> None:
        """Validate that the configuration is complete.
        
        Raises:
            ValueError: If any required configuration is missing
        """
        if not self.source_token:
            raise ValueError("Source API token is required")
        if not self.source_url:
            raise ValueError("Source backend URL is required")
        if not self.target_token:
            raise ValueError("Target API token is required")
        if not self.target_url:
            raise ValueError("Target backend URL is required")
    
    def get_source_headers(self) -> Dict[str, str]:
        """Get headers for source backend API requests.
        
        Returns:
            Dictionary of HTTP headers
        """
        return {
            "Authorization": f"apiToken {self.source_token}",
            "Content-Type": "application/json"
        }
    
    def get_target_headers(self) -> Dict[str, str]:
        """Get headers for target backend API requests.
        
        Returns:
            Dictionary of HTTP headers
        """
        return {
            "Authorization": f"apiToken {self.target_token}",
            "Content-Type": "application/json"
        }

# Made with Bob
