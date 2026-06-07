"""
LakeBase API Client for GitMats.

Provides HTTP client for LakeBase (Lakeon PostgreSQL) API.
Handles authentication, error handling, and request/response processing.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from urllib.parse import urljoin

import httpx


@dataclass
class LakeBaseConfig:
    """Configuration for LakeBase connection."""
    api_url: str = "https://api.dbay.cloud:8443/api/v1"
    database_id: str = ""
    api_token: str = ""
    branch_prefix: str = "gitmats-"
    parent_branch: str = "main"
    start_compute_on_create: bool = False
    auto_suspend_timeout: str = "5m"
    
    @classmethod
    def from_env(cls) -> "LakeBaseConfig":
        """Create configuration from environment variables."""
        return cls(
            api_url=os.environ.get("LAKEBASE_API_URL", cls.api_url),
            database_id=os.environ.get("LAKEBASE_DATABASE_ID", ""),
            api_token=os.environ.get("LAKEBASE_API_TOKEN", ""),
            branch_prefix=os.environ.get("LAKEBASE_BRANCH_PREFIX", cls.branch_prefix),
            parent_branch=os.environ.get("LAKEBASE_PARENT_BRANCH", cls.parent_branch),
        )
    
    def validate(self) -> list[str]:
        """Validate configuration. Returns list of errors."""
        errors = []
        
        if not self.database_id:
            errors.append("database_id is required")
        
        if not self.api_token:
            errors.append("api_token is required (set LAKEBASE_API_TOKEN)")
        
        if not self.api_url:
            errors.append("api_url is required")
        
        return errors


class LakeBaseError(Exception):
    """Base exception for LakeBase operations."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class LakeBaseClient:
    """
    HTTP client for LakeBase API.
    
    Provides methods for:
    - Branch management (create, delete, list)
    - Version management (create, list, get)
    - Diff operations (schema, data)
    - Restore operations
    """
    
    def __init__(self, config: LakeBaseConfig) -> None:
        """
        Initialize LakeBase client.
        
        Args:
            config: LakeBase configuration.
        """
        self.config = config
        self._client: Optional[httpx.Client] = None
    
    @property
    def client(self) -> httpx.Client:
        """Get HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.config.api_url,
                headers={
                    "Authorization": f"Bearer {self.config.api_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client
    
    def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
    
    def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:
        """
        Make API request.
        
        Args:
            method: HTTP method.
            path: API path.
            **kwargs: Additional request parameters.
        
        Returns:
            Response JSON.
        
        Raises:
            LakeBaseError: On API error.
        """
        try:
            response = self.client.request(method, path, **kwargs)
            
            if response.status_code >= 400:
                try:
                    error_data = response.json()
                except json.JSONDecodeError:
                    error_data = {"message": response.text}
                
                raise LakeBaseError(
                    message=f"API error: {error_data.get('message', response.text)}",
                    status_code=response.status_code,
                    response=error_data,
                )
            
            if response.status_code == 204:
                return {}
            
            return response.json()
        
        except httpx.TimeoutException as e:
            raise LakeBaseError(f"Request timeout: {e}")
        except httpx.RequestError as e:
            raise LakeBaseError(f"Request error: {e}")
    
    # ===== Branch Operations =====
    
    def create_branch(
        self,
        name: str,
        parent_branch: Optional[str] = None,
        start_compute: bool = False,
    ) -> dict:
        """
        Create a new branch.
        
        Args:
            name: Branch name.
            parent_branch: Parent branch name (default from config).
            start_compute: Whether to start compute immediately.
        
        Returns:
            Branch info dictionary.
        """
        parent = parent_branch or self.config.parent_branch
        
        return self._request(
            "POST",
            f"/databases/{self.config.database_id}/branches",
            json={
                "name": name,
                "parent_branch_name": parent,
                "start_compute": start_compute,
            },
        )
    
    def get_branch(self, branch_id: str) -> dict:
        """
        Get branch info.
        
        Args:
            branch_id: Branch identifier.
        
        Returns:
            Branch info dictionary.
        """
        return self._request(
            "GET",
            f"/databases/{self.config.database_id}/branches/{branch_id}",
        )
    
    def list_branches(self) -> list[dict]:
        """
        List all branches.
        
        Returns:
            List of branch info dictionaries.
        """
        response = self._request(
            "GET",
            f"/databases/{self.config.database_id}/branches",
        )
        return response.get("branches", [])
    
    def delete_branch(self, branch_id: str) -> bool:
        """
        Delete a branch.
        
        Args:
            branch_id: Branch identifier.
        
        Returns:
            True if deleted.
        """
        try:
            self._request(
                "DELETE",
                f"/databases/{self.config.database_id}/branches/{branch_id}",
            )
            return True
        except LakeBaseError as e:
            if e.status_code == 400:
                # Default branch cannot be deleted
                return False
            raise
    
    # ===== Version Operations =====
    
    def create_version(
        self,
        branch_id: str,
        name: str,
        description: Optional[str] = None,
        at: str = "current",
    ) -> dict:
        """
        Create a version snapshot.
        
        Args:
            branch_id: Branch identifier.
            name: Version name.
            description: Version description.
            at: Version position ("current" or specific LSN).
        
        Returns:
            Version info dictionary.
        """
        body = {
            "name": name,
            "at": at,
        }
        
        if description:
            body["description"] = description
        
        return self._request(
            "POST",
            f"/databases/{self.config.database_id}/branches/{branch_id}/versions",
            json=body,
        )
    
    def list_versions(self, branch_id: str, limit: int = 100) -> list[dict]:
        """
        List versions for a branch.
        
        Args:
            branch_id: Branch identifier.
            limit: Maximum versions to return.
        
        Returns:
            List of version info dictionaries.
        """
        response = self._request(
            "GET",
            f"/databases/{self.config.database_id}/branches/{branch_id}/versions",
            params={"limit": limit},
        )
        return response.get("versions", [])
    
    def get_version(self, branch_id: str, version_id: str) -> dict:
        """
        Get version info.
        
        Args:
            branch_id: Branch identifier.
            version_id: Version identifier.
        
        Returns:
            Version info dictionary.
        """
        return self._request(
            "GET",
            f"/databases/{self.config.database_id}/branches/{branch_id}/versions/{version_id}",
        )
    
    # ===== Diff Operations =====
    
    def diff_schema(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
    ) -> dict:
        """
        Get schema diff between two versions/branches.
        
        Args:
            source_type: "version" or "branch".
            source_id: Source identifier.
            target_type: "version" or "branch".
            target_id: Target identifier.
        
        Returns:
            Schema diff dictionary.
        """
        return self._request(
            "GET",
            f"/databases/{self.config.database_id}/diff/schema",
            params={
                "source_type": source_type,
                "source_id": source_id,
                "target_type": target_type,
                "target_id": target_id,
            },
        )
    
    def diff_data(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        table_name: Optional[str] = None,
        limit: int = 1000,
    ) -> dict:
        """
        Get data diff between two versions/branches.
        
        Args:
            source_type: "version" or "branch".
            source_id: Source identifier.
            target_type: "version" or "branch".
            target_id: Target identifier.
            table_name: Specific table to diff.
            limit: Maximum rows to return.
        
        Returns:
            Data diff dictionary.
        """
        params = {
            "source_type": source_type,
            "source_id": source_id,
            "target_type": target_type,
            "target_id": target_id,
            "limit": limit,
        }
        
        if table_name:
            params["table_name"] = table_name
        
        return self._request(
            "GET",
            f"/databases/{self.config.database_id}/diff/data",
            params=params,
        )
    
    # ===== Restore Operations =====
    
    def restore_version(
        self,
        branch_id: str,
        target_version_id: str,
    ) -> dict:
        """
        Restore branch to a specific version.
        
        Args:
            branch_id: Branch identifier.
            target_version_id: Target version identifier.
        
        Returns:
            Restore info dictionary with new timeline ID.
        """
        return self._request(
            "POST",
            f"/databases/{self.config.database_id}/branches/{branch_id}/restore",
            json={"target_version_id": target_version_id},
        )
    
    # ===== Compute Operations =====
    
    def start_compute(self, branch_id: str) -> dict:
        """
        Start compute for a branch.
        
        Args:
            branch_id: Branch identifier.
        
        Returns:
            Compute info dictionary.
        """
        return self._request(
            "POST",
            f"/databases/{self.config.database_id}/branches/{branch_id}/compute/start",
        )
    
    def suspend_compute(self, branch_id: str) -> dict:
        """
        Suspend compute for a branch.
        
        Args:
            branch_id: Branch identifier.
        
        Returns:
            Compute info dictionary.
        """
        return self._request(
            "POST",
            f"/databases/{self.config.database_id}/branches/{branch_id}/compute/suspend",
        )
    
    def get_compute_status(self, branch_id: str) -> dict:
        """
        Get compute status for a branch.
        
        Args:
            branch_id: Branch identifier.
        
        Returns:
            Compute status dictionary.
        """
        return self._request(
            "GET",
            f"/databases/{self.config.database_id}/branches/{branch_id}/compute",
        )