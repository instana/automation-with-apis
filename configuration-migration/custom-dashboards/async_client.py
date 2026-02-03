"""Async HTTP client wrapper with connection pooling and retry logic."""

import aiohttp
import asyncio
from aiohttp_retry import RetryClient, ExponentialRetry
from typing import Dict, Any, Optional
import ssl


class AsyncHTTPClient:
    """Manages async HTTP sessions with retry and rate limiting."""
    
    def __init__(self, verify_ssl: bool = True, timeout: int = 30, max_retries: int = 3):
        """Initialize the async HTTP client.
        
        Args:
            verify_ssl: Whether to verify SSL certificates
            timeout: Timeout for requests in seconds
            max_retries: Maximum number of retry attempts
        """
        self.verify_ssl = verify_ssl
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.session: Optional[aiohttp.ClientSession] = None
        self.retry_client: Optional[RetryClient] = None
        
    async def __aenter__(self):
        """Enter async context manager."""
        # Configure SSL context
        ssl_context = ssl.create_default_context()
        if not self.verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        
        # Create connector with connection pooling
        connector = aiohttp.TCPConnector(
            ssl=ssl_context if self.verify_ssl else False,
            limit=100,  # Connection pool size
            limit_per_host=30
        )
        
        # Create session
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout
        )
        
        # Create retry client with exponential backoff
        retry_options = ExponentialRetry(
            attempts=self.max_retries,
            start_timeout=1.0,
            max_timeout=30.0,
            factor=2.0,
            statuses={500, 502, 503, 504, 429}  # Retry on these status codes
        )
        
        self.retry_client = RetryClient(
            client_session=self.session,
            retry_options=retry_options
        )
        
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        if self.retry_client:
            await self.retry_client.close()
        if self.session:
            await self.session.close()
    
    async def get(self, url: str, headers: Dict[str, str]) -> aiohttp.ClientResponse:
        """Perform async GET request with retry logic.
        
        Args:
            url: URL to request
            headers: HTTP headers
            
        Returns:
            Response object
        """
        if not self.retry_client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        
        async with self.retry_client.get(url, headers=headers) as response:
            response.raise_for_status()
            return response
    
    async def post(self, url: str, headers: Dict[str, str], json: Dict[str, Any]) -> aiohttp.ClientResponse:
        """Perform async POST request with retry logic.
        
        Args:
            url: URL to request
            headers: HTTP headers
            json: JSON payload
            
        Returns:
            Response object
        """
        if not self.retry_client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        
        async with self.retry_client.post(url, headers=headers, json=json) as response:
            response.raise_for_status()
            return response
    
    async def put(self, url: str, headers: Dict[str, str], json: Dict[str, Any]) -> aiohttp.ClientResponse:
        """Perform async PUT request with retry logic.
        
        Args:
            url: URL to request
            headers: HTTP headers
            json: JSON payload
            
        Returns:
            Response object
        """
        if not self.retry_client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        
        async with self.retry_client.put(url, headers=headers, json=json) as response:
            response.raise_for_status()
            return response

# Made with Bob
