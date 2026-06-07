"""
LakeBase Backend for GitMats.

Delegates version control operations to LakeBase (Lakeon PostgreSQL) API.
Maps GitMats concepts to LakeBase:
- Workspace → LakeBase Branch (created from database's main branch)
- Commit → LakeBase Version (named snapshot at LSN)
- Diff → LakeBase Schema/Data Diff API
- Restore → LakeBase Restore API
"""

from datetime import datetime
from typing import Optional

from gitmats.backends.interface import (
    VersioningBackend,
    BranchResult,
    CommitResult,
    VersionInfo,
    DiffResult,
    RestoreResult,
    DeleteResult,
    FileChange,
)
from gitmats.backends.lakebase_client import LakeBaseClient, LakeBaseConfig, LakeBaseError
from gitmats.models import Workspace, WorkspaceType
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager


class LakeBaseBackend(VersioningBackend):
    """
    LakeBase (Lakeon PostgreSQL) versioning backend.
    
    When configured, GitMats delegates commit storage to LakeBase API,
    enabling database-native version control.
    """
    
    def __init__(
        self,
        config: LakeBaseConfig,
        storage_manager: StorageManager,
        metadata_manager: MetadataManager,
    ) -> None:
        """
        Initialize LakeBase backend.
        
        Args:
            config: LakeBase configuration.
            storage_manager: Storage manager for paths.
            metadata_manager: Metadata manager for tracking.
        """
        self.config = config
        self.storage_manager = storage_manager
        self.metadata_manager = metadata_manager
        self.client = LakeBaseClient(config)
    
    def create_workspace_branch(self, workspace: Workspace) -> BranchResult:
        """
        Create LakeBase branch for GitMats workspace.
        
        API call: POST /api/v1/databases/{database_id}/branches
        
        The branch inherits from database's main branch, providing:
        - Zero-copy initial state (CoW at PostgreSQL level)
        - Independent timeline for workspace modifications
        - Ability to promote back to main if desired
        """
        # Validate configuration
        errors = self.config.validate()
        if errors:
            return BranchResult(
                status="error",
                message=f"Configuration errors: {', '.join(errors)}",
            )
        
        # Generate branch name
        branch_name = f"{self.config.branch_prefix}{workspace.workspace_id}"
        
        try:
            branch = self.client.create_branch(
                name=branch_name,
                parent_branch=self.config.parent_branch,
                start_compute=self.config.start_compute_on_create,
            )
            
            # Store branch metadata in workspace
            workspace.backend_meta = {
                "lakebase_branch_id": branch.get("id"),
                "lakebase_timeline_id": branch.get("neon_timeline_id"),
                "lakebase_branch_name": branch.get("name"),
                "connection_uri": branch.get("connection_uri"),
            }
            
            # Update workspace in metadata
            self.metadata_manager.update_workspace(workspace)
            
            return BranchResult(
                branch_id=branch.get("id"),
                connection_uri=branch.get("connection_uri"),
                status="created",
            )
        
        except LakeBaseError as e:
            return BranchResult(
                status="error",
                message=f"Failed to create branch: {e}",
            )
    
    def commit(
        self,
        workspace: Workspace,
        message: str,
        files: Optional[list[FileChange]] = None,
        author: Optional[str] = None,
    ) -> CommitResult:
        """
        Create LakeBase version as commit snapshot.
        
        Strategy:
        1. COW engine ensures all modified files are in copies/
        2. For file-based workspace: sync copies metadata to LakeBase
        3. Trigger LakeBase version creation with checkpoint
        """
        branch_id = workspace.backend_meta.get("lakebase_branch_id")
        if not branch_id:
            return CommitResult(
                status="error",
                message="Workspace has no LakeBase branch",
            )
        
        # Build description
        description = f"GitMats workspace {workspace.workspace_id}"
        if files:
            description += f" | {len(files)} files changed"
        
        try:
            version = self.client.create_version(
                branch_id=branch_id,
                name=message,
                description=description,
                at="current",
            )
            
            return CommitResult(
                version_id=version.get("id"),
                timestamp=datetime.fromisoformat(version.get("created_at", "")) if version.get("created_at") else None,
                lsn=version.get("lsn"),
                status="committed",
            )
        
        except LakeBaseError as e:
            return CommitResult(
                status="error",
                message=f"Failed to create version: {e}",
            )
    
    def list_versions(self, workspace: Workspace, limit: int = 10) -> list[VersionInfo]:
        """
        List all versions for workspace branch.
        
        API call: GET /api/v1/databases/{database_id}/branches/{branch_id}/versions
        """
        branch_id = workspace.backend_meta.get("lakebase_branch_id")
        if not branch_id:
            return []
        
        try:
            versions = self.client.list_versions(branch_id, limit=limit)
            
            return [
                VersionInfo(
                    version_id=v.get("id", ""),
                    name=v.get("name"),
                    description=v.get("description"),
                    lsn=v.get("lsn"),
                    created_at=datetime.fromisoformat(v.get("created_at", "")) if v.get("created_at") else None,
                    created_by=v.get("created_by"),
                    message=v.get("name"),  # Use name as message
                )
                for v in versions
            ]
        
        except LakeBaseError:
            return []
    
    def get_version(self, workspace: Workspace, version_id: str) -> Optional[VersionInfo]:
        """
        Get specific version details.
        
        API call: GET /api/v1/databases/{database_id}/branches/{branch_id}/versions/{version_id}
        """
        branch_id = workspace.backend_meta.get("lakebase_branch_id")
        if not branch_id:
            return None
        
        try:
            v = self.client.get_version(branch_id, version_id)
            
            return VersionInfo(
                version_id=v.get("id", ""),
                name=v.get("name"),
                description=v.get("description"),
                lsn=v.get("lsn"),
                created_at=datetime.fromisoformat(v.get("created_at", "")) if v.get("created_at") else None,
                created_by=v.get("created_by"),
                message=v.get("name"),
            )
        
        except LakeBaseError:
            return None
    
    def diff_versions(
        self,
        workspace: Workspace,
        source_id: str,
        target_id: str,
    ) -> DiffResult:
        """
        Compare two versions using LakeBase diff API.
        
        API calls:
        - GET /api/v1/databases/{database_id}/diff/schema
        - GET /api/v1/databases/{database_id}/diff/data
        """
        branch_id = workspace.backend_meta.get("lakebase_branch_id")
        if not branch_id:
            return DiffResult(
                source_id=source_id,
                target_id=target_id,
                summary="No LakeBase branch",
            )
        
        try:
            # Schema diff
            schema_diff = self.client.diff_schema(
                source_type="version",
                source_id=source_id,
                target_type="version",
                target_id=target_id,
            )
            
            # Data diff
            data_diff = self.client.diff_data(
                source_type="version",
                source_id=source_id,
                target_type="version",
                target_id=target_id,
                limit=1000,
            )
            
            # Extract changed files from data diff
            files_changed = []
            if data_diff.get("changes"):
                for change in data_diff.get("changes", []):
                    if change.get("table") == "gitmats_file_metadata":
                        files_changed.append(change.get("key", ""))
            
            # Generate summary
            schema_changes = len(schema_diff.get("changes", []))
            data_changes = len(data_diff.get("changes", []))
            summary = f"{schema_changes} schema changes, {data_changes} data changes, {len(files_changed)} files changed"
            
            return DiffResult(
                source_id=source_id,
                target_id=target_id,
                schema_diff=schema_diff,
                data_diff=data_diff,
                files_changed=files_changed,
                summary=summary,
            )
        
        except LakeBaseError as e:
            return DiffResult(
                source_id=source_id,
                target_id=target_id,
                summary=f"Diff failed: {e}",
            )
    
    def restore_version(
        self,
        workspace: Workspace,
        version_id: str,
    ) -> RestoreResult:
        """
        Restore workspace to specific version state.
        
        API call: POST /api/v1/databases/{database_id}/branches/{branch_id}/restore
        
        For file-based workspace:
        1. LakeBase restore creates new timeline
        2. Rebuild COW copies from restored metadata
        3. Update symlinks accordingly
        """
        branch_id = workspace.backend_meta.get("lakebase_branch_id")
        if not branch_id:
            return RestoreResult(
                version_id=version_id,
                status="error",
                message="No LakeBase branch",
            )
        
        try:
            restore_info = self.client.restore_version(branch_id, version_id)
            
            # Update workspace metadata
            workspace.backend_meta["lakebase_timeline_id"] = restore_info.get("new_timeline_id")
            self.metadata_manager.update_workspace(workspace)
            
            return RestoreResult(
                version_id=version_id,
                new_timeline_id=restore_info.get("new_timeline_id"),
                backup_branch_id=restore_info.get("backup_branch_id"),
                status="restored",
            )
        
        except LakeBaseError as e:
            return RestoreResult(
                version_id=version_id,
                status="error",
                message=f"Restore failed: {e}",
            )
    
    def delete_branch(self, workspace: Workspace) -> DeleteResult:
        """
        Delete workspace branch on destroy.
        
        API call: DELETE /api/v1/databases/{database_id}/branches/{branch_id}
        
        Note: LakeBase prevents deletion of default branch
        """
        branch_id = workspace.backend_meta.get("lakebase_branch_id")
        if not branch_id:
            return DeleteResult(status="no_branch")
        
        try:
            deleted = self.client.delete_branch(branch_id)
            
            if deleted:
                return DeleteResult(status="deleted")
            else:
                return DeleteResult(
                    status="protected",
                    message="Default branch cannot be deleted",
                )
        
        except LakeBaseError as e:
            return DeleteResult(
                status="error",
                message=f"Failed to delete branch: {e}",
            )
    
    def get_status(self, workspace: Workspace) -> dict:
        """
        Get workspace status.
        
        Returns LakeBase-specific status info.
        """
        branch_id = workspace.backend_meta.get("lakebase_branch_id")
        if not branch_id:
            return {
                "backend": "lakebase",
                "status": "no_branch",
            }
        
        try:
            branch = self.client.get_branch(branch_id)
            compute_status = self.client.get_compute_status(branch_id)
            
            return {
                "backend": "lakebase",
                "branch_id": branch_id,
                "branch_name": branch.get("name"),
                "timeline_id": branch.get("neon_timeline_id"),
                "compute_status": compute_status.get("status"),
                "connection_uri": branch.get("connection_uri"),
            }
        
        except LakeBaseError as e:
            return {
                "backend": "lakebase",
                "status": "error",
                "message": str(e),
            }
    
    def sync_to_original(self, workspace: Workspace) -> bool:
        """
        LakeBase backend does not support sync to original.
        
        Use promote_to_parent instead for merging changes.
        """
        return False
    
    def close(self) -> None:
        """Close LakeBase client."""
        self.client.close()