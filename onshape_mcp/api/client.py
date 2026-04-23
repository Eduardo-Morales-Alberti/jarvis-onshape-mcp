"""Onshape API client for REST API communication."""

import asyncio
import base64
import time
import httpx
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel
from loguru import logger


class OnshapeCredentials(BaseModel):
    """Onshape API key credentials (paid plans)."""

    access_key: str
    secret_key: str
    base_url: str = "https://cad.onshape.com"


class OnshapeOAuthCredentials(BaseModel):
    """Onshape OAuth 2.0 credentials (free plan compatible)."""

    client_id: str
    client_secret: str
    base_url: str = "https://cad.onshape.com"


class OnshapeClient:
    """Client for interacting with Onshape REST API.

    Use as an async context manager to ensure proper cleanup:
        async with OnshapeClient(credentials) as client:
            result = await client.get("/api/v9/documents")
    """

    def __init__(self, credentials: Union[OnshapeCredentials, OnshapeOAuthCredentials]):
        """Initialize the Onshape client.

        Args:
            credentials: API key credentials or OAuth credentials.
        """
        self.credentials = credentials
        self.base_url = credentials.base_url
        self._client: Optional[httpx.AsyncClient] = None
        self._own_client = False
        # Populated on first use when in OAuth mode (loaded from disk / refreshed).
        self._oauth_tokens = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=30.0)
        self._own_client = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures cleanup."""
        await self.close()
        return False

    def _ensure_client(self):
        """Ensure HTTP client is initialized."""
        if self._client is None:
            # Create client if not using context manager (backwards compatibility)
            self._client = httpx.AsyncClient(timeout=30.0)
            self._own_client = True

    async def _ensure_valid_token(self) -> None:
        """Refresh OAuth access token if expired (no-op for API-key mode)."""
        if not isinstance(self.credentials, OnshapeOAuthCredentials):
            return

        if self._oauth_tokens is None:
            from .oauth import load_tokens
            self._oauth_tokens = load_tokens()

        if self._oauth_tokens is None:
            raise RuntimeError(
                "No OAuth tokens found. Run `onshape-mcp --auth` to authenticate first."
            )

        if time.time() >= self._oauth_tokens.expires_at - 60:
            from .oauth import refresh_access_token, save_tokens
            creds = self.credentials
            self._oauth_tokens = await asyncio.to_thread(
                refresh_access_token,
                creds.client_id,
                creds.client_secret,
                self._oauth_tokens.refresh_token,
            )
            save_tokens(self._oauth_tokens)

    def _get_auth_header(self) -> str:
        """Return the Authorization header value for the current credential mode."""
        if isinstance(self.credentials, OnshapeOAuthCredentials):
            if self._oauth_tokens is None:
                raise RuntimeError("OAuth tokens not loaded. Call _ensure_valid_token() first.")
            return f"Bearer {self._oauth_tokens.access_token}"
        auth_string = f"{self.credentials.access_key}:{self.credentials.secret_key}"
        encoded = base64.b64encode(auth_string.encode()).decode()
        return f"Basic {encoded}"

    def _sanitize_for_logging(self, data: Any, max_length: int = 200) -> str:
        """Sanitize sensitive data for logging.

        Args:
            data: Data to sanitize
            max_length: Maximum length of output string

        Returns:
            Sanitized string safe for logging
        """
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                if k.lower() in {
                    "authorization",
                    "api_key",
                    "secret",
                    "password",
                    "token",
                    "access_key",
                    "secret_key",
                }:
                    sanitized[k] = "***REDACTED***"
                else:
                    sanitized[k] = v
            return str(sanitized)[:max_length]

        result = str(data)
        if len(result) > max_length:
            return result[:max_length] + "... (truncated)"
        return result

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a GET request to Onshape API.

        Args:
            path: API endpoint path (e.g., "/api/v9/documents")
            params: Query parameters

        Returns:
            JSON response data
        """
        url = f"{self.base_url}{path}"
        await self._ensure_valid_token()
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept": "application/json;charset=UTF-8; qs=0.09",
        }

        self._ensure_client()
        logger.debug(f"GET {url} with params: {self._sanitize_for_logging(params)}")
        response = await self._client.get(url, params=params, headers=headers)
        response.raise_for_status()
        result = response.json()
        logger.debug(f"GET {url} response: {self._sanitize_for_logging(result, max_length=500)}")
        return result

    async def get_raw(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        follow_redirects: bool = True,
    ) -> bytes:
        """Make a GET request that returns the raw response body.

        Used for binary payloads such as translation downloads and thumbnails
        where the response is not JSON.

        Args:
            path: API endpoint path
            params: Query parameters
            follow_redirects: Whether to follow 302s (Onshape often redirects
                external-data downloads to a signed URL)

        Returns:
            Raw response bytes
        """
        url = f"{self.base_url}{path}"
        await self._ensure_valid_token()
        headers = {
            "Authorization": self._get_auth_header(),
        }

        self._ensure_client()
        logger.debug(f"GET (raw) {url} with params: {self._sanitize_for_logging(params)}")
        response = await self._client.get(
            url, params=params, headers=headers, follow_redirects=follow_redirects
        )
        response.raise_for_status()
        logger.debug(f"GET (raw) {url} returned {len(response.content)} bytes")
        return response.content

    async def post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a POST request to Onshape API.

        Args:
            path: API endpoint path
            data: JSON body data
            params: Query parameters

        Returns:
            JSON response data
        """
        url = f"{self.base_url}{path}"
        await self._ensure_valid_token()
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept": "application/json;charset=UTF-8; qs=0.09",
            "Content-Type": "application/json;charset=UTF-8; qs=0.09",
        }

        self._ensure_client()
        logger.debug(f"POST {url} with params: {self._sanitize_for_logging(params)}")
        logger.debug(f"POST {url} data: {self._sanitize_for_logging(data, max_length=1000)}")
        response = await self._client.post(url, json=data, params=params, headers=headers)

        # Log error details if request failed
        if response.status_code >= 400:
            try:
                error_body = response.json()
                logger.error(
                    f"POST {url} failed with status {response.status_code}: {self._sanitize_for_logging(error_body)}"
                )
            except Exception:
                logger.error(
                    f"POST {url} failed with status {response.status_code}: {response.text[:500]}"
                )

        response.raise_for_status()
        if not response.content:
            logger.debug(f"POST {url} returned empty body (status {response.status_code})")
            return {}
        result = response.json()
        logger.debug(f"POST {url} response: {self._sanitize_for_logging(result, max_length=500)}")
        return result

    async def delete(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make a DELETE request to Onshape API.

        Args:
            path: API endpoint path
            params: Query parameters

        Returns:
            JSON response data
        """
        url = f"{self.base_url}{path}"
        await self._ensure_valid_token()
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept": "application/json;charset=UTF-8; qs=0.09",
        }

        self._ensure_client()
        response = await self._client.delete(url, params=params, headers=headers)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    async def close(self):
        """Close the HTTP client and clean up resources."""
        if self._client and self._own_client:
            await self._client.aclose()
            self._client = None
