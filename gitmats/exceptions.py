"""
GitMats Exceptions Module.

Provides custom exception hierarchy for user-friendly error messages
and structured error handling.
"""

from typing import Optional


class GitMatsError(Exception):
    """Base exception for all GitMats errors."""
    
    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code or "UNKNOWN"
        self.details = details or {}
    
    def __str__(self) -> str:
        return self.message
    
    def to_dict(self) -> dict:
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


class WorkspaceNotFoundError(GitMatsError):
    """Raised when a workspace is not found."""
    
    def __init__(self, workspace_id: str):
        super().__init__(
            message=f"Workspace '{workspace_id}' not found. Use 'gmt list' to see available workspaces.",
            code="WORKSPACE_NOT_FOUND",
            details={"workspace_id": workspace_id},
        )


class WorkspaceAlreadyExistsError(GitMatsError):
    """Raised when trying to create a workspace that already exists."""
    
    def __init__(self, workspace_id: str, existing_path: Optional[str] = None):
        details = {"workspace_id": workspace_id}
        if existing_path:
            details["existing_path"] = existing_path
        
        super().__init__(
            message=f"Workspace '{workspace_id}' already exists. Use a different ID or destroy the existing workspace first.",
            code="WORKSPACE_EXISTS",
            details=details,
        )


class WorkspaceLockedError(GitMatsError):
    """Raised when trying to modify a locked workspace."""
    
    def __init__(self, workspace_id: str, locked_by: Optional[str] = None):
        details = {"workspace_id": workspace_id}
        if locked_by:
            details["locked_by"] = locked_by
        
        msg = f"Workspace '{workspace_id}' is locked and cannot be modified."
        if locked_by:
            msg += f" Locked by: {locked_by}"
        
        super().__init__(
            message=msg,
            code="WORKSPACE_LOCKED",
            details=details,
        )


class InvalidWorkspaceIdError(GitMatsError):
    """Raised when workspace ID doesn't match the required pattern."""
    
    def __init__(self, workspace_id: str, pattern: str = "[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}"):
        super().__init__(
            message=f"Invalid workspace ID '{workspace_id}'. Must match pattern: {pattern}",
            code="INVALID_WORKSPACE_ID",
            details={"workspace_id": workspace_id, "pattern": pattern},
        )


class OriginalPathNotFoundError(GitMatsError):
    """Raised when the original path doesn't exist."""
    
    def __init__(self, path: str):
        super().__init__(
            message=f"Original path '{path}' does not exist or is not accessible.",
            code="ORIGINAL_NOT_FOUND",
            details={"path": path},
        )


class OriginalNotGitError(GitMatsError):
    """Raised when trying to use Git mode on a non-Git directory."""
    
    def __init__(self, path: str):
        super().__init__(
            message=f"Original path '{path}' is not a Git repository. Use --git-mode=standalone to create an independent repository, or initialize Git in the original directory first.",
            code="ORIGINAL_NOT_GIT",
            details={"path": path},
        )


class GitOperationError(GitMatsError):
    """Raised when a Git operation fails."""
    
    def __init__(
        self,
        operation: str,
        message: str,
        workspace_id: Optional[str] = None,
    ):
        details = {"operation": operation}
        if workspace_id:
            details["workspace_id"] = workspace_id
        
        super().__init__(
            message=f"Git operation '{operation}' failed: {message}",
            code="GIT_ERROR",
            details=details,
        )


class BackendError(GitMatsError):
    """Raised when versioning backend operation fails."""
    
    def __init__(
        self,
        backend: str,
        operation: str,
        message: str,
        workspace_id: Optional[str] = None,
    ):
        details = {"backend": backend, "operation": operation}
        if workspace_id:
            details["workspace_id"] = workspace_id
        
        super().__init__(
            message=f"Backend '{backend}' error during '{operation}': {message}",
            code="BACKEND_ERROR",
            details=details,
        )


class ConfigurationError(GitMatsError):
    """Raised when configuration is invalid or missing."""
    
    def __init__(self, message: str, key: Optional[str] = None):
        details = {}
        if key:
            details["config_key"] = key
        
        super().__init__(
            message=f"Configuration error: {message}",
            code="CONFIG_ERROR",
            details=details,
        )


class COWError(GitMatsError):
    """Raised when COW engine operation fails."""
    
    def __init__(
        self,
        operation: str,
        path: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ):
        details = {"operation": operation}
        if path:
            details["path"] = path
        if workspace_id:
            details["workspace_id"] = workspace_id
        
        super().__init__(
            message=f"COW engine error during '{operation}'",
            code="COW_ERROR",
            details=details,
        )


class MetadataError(GitMatsError):
    """Raised when metadata operation fails."""
    
    def __init__(self, message: str, workspace_id: Optional[str] = None):
        details = {}
        if workspace_id:
            details["workspace_id"] = workspace_id
        
        super().__init__(
            message=f"Metadata error: {message}",
            code="METADATA_ERROR",
            details=details,
        )


class WorkspaceIntegrityError(GitMatsError):
    """Raised when workspace integrity validation fails."""
    
    def __init__(
        self,
        workspace_id: str,
        issues: list[str],
    ):
        super().__init__(
            message=f"Workspace '{workspace_id}' has integrity issues: {', '.join(issues)}",
            code="INTEGRITY_ERROR",
            details={"workspace_id": workspace_id, "issues": issues},
        )


class PermissionError(GitMatsError):
    """Raised when permission is denied for an operation."""
    
    def __init__(self, path: str, operation: str):
        super().__init__(
            message=f"Permission denied for '{operation}' on '{path}'",
            code="PERMISSION_DENIED",
            details={"path": path, "operation": operation},
        )


class StorageError(GitMatsError):
    """Raised when storage operation fails."""
    
    def __init__(self, message: str, path: Optional[str] = None):
        details = {}
        if path:
            details["path"] = path
        
        super().__init__(
            message=f"Storage error: {message}",
            code="STORAGE_ERROR",
            details=details,
        )