"""
Metadata management for GitMats.

Handles workspace registry and per-workspace metadata using SQLite.
"""

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from gitmats.models import (
    FileState,
    GitCommit,
    OperationLog,
    OperationType,
    Workspace,
    WorkspaceConfig,
    WorkspaceStatus,
    WorkspaceType,
    FileStatus,
    GitMode,
    CommitType,
)


# Global registry database schema
REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    workspace_dir TEXT NOT NULL,
    git_dir TEXT NOT NULL,
    copies_dir TEXT NOT NULL,
    metadata_db TEXT NOT NULL,
    workspace_type TEXT NOT NULL CHECK(workspace_type IN ('inherited', 'standalone')),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'locked', 'destroyed', 'archived')),
    created_at REAL NOT NULL,
    last_accessed REAL,
    created_by TEXT,
    git_mode TEXT CHECK(git_mode IN ('inherited', 'standalone')),
    git_branch TEXT,
    git_head TEXT,
    config_json TEXT,
    backend_meta_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_original_path ON workspaces(original_path);
CREATE INDEX IF NOT EXISTS idx_status ON workspaces(status);
CREATE INDEX IF NOT EXISTS idx_created_at ON workspaces(created_at);

CREATE TABLE IF NOT EXISTS workspace_stats (
    workspace_id TEXT PRIMARY KEY,
    total_files INTEGER DEFAULT 0,
    linked_files INTEGER DEFAULT 0,
    copied_files INTEGER DEFAULT 0,
    new_files INTEGER DEFAULT 0,
    deleted_files INTEGER DEFAULT 0,
    disk_usage_bytes INTEGER DEFAULT 0,
    original_size_bytes INTEGER DEFAULT 0,
    savings_ratio REAL DEFAULT 0,
    last_updated REAL,
    
    FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workspace_history (
    workspace_id TEXT,
    operation TEXT NOT NULL,
    timestamp REAL NOT NULL,
    details_json TEXT,
    
    FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workspace_history ON workspace_history(workspace_id, timestamp);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL
);
"""

# Per-workspace metadata schema
WORKSPACE_SCHEMA = """
CREATE TABLE IF NOT EXISTS file_state (
    relative_path TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK(status IN ('linked', 'copied', 'new', 'deleted', 'unknown')),
    
    -- Original file info
    original_hash TEXT,
    original_size INTEGER,
    original_mtime REAL,
    
    -- COW copy info
    cow_path TEXT,
    cow_hash TEXT,
    cow_size INTEGER,
    cow_mtime REAL,
    
    -- Modification tracking
    first_modified_at REAL,
    last_modified_at REAL,
    modification_count INTEGER DEFAULT 0,
    
    -- Git integration
    git_tracked INTEGER DEFAULT 1,
    git_blob_sha TEXT,
    git_staged INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_file_status ON file_state(status);
CREATE INDEX IF NOT EXISTS idx_git_staged ON file_state(git_staged);

CREATE TABLE IF NOT EXISTS git_commits (
    commit_sha TEXT PRIMARY KEY,
    commit_message TEXT,
    tree_sha TEXT,
    parent_sha TEXT,
    
    author_name TEXT,
    author_email TEXT,
    authored_at REAL,
    
    committer_name TEXT,
    committer_email TEXT,
    committed_at REAL,
    
    files_changed INTEGER,
    insertions INTEGER,
    deletions INTEGER,
    
    commit_type TEXT CHECK(commit_type IN ('user', 'cow_sync', 'base', 'sync')),
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_committed_at ON git_commits(committed_at);
CREATE INDEX IF NOT EXISTS idx_commit_type ON git_commits(commit_type);

CREATE TABLE IF NOT EXISTS git_refs (
    ref_name TEXT PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS operations_log (
    operation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type TEXT NOT NULL,
    relative_path TEXT,
    
    timestamp REAL NOT NULL,
    duration_ms INTEGER,
    
    success INTEGER NOT NULL,
    error_message TEXT,
    
    details_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_operations_timestamp ON operations_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_operations_type ON operations_log(operation_type);
CREATE INDEX IF NOT EXISTS idx_operations_path ON operations_log(relative_path);

CREATE TABLE IF NOT EXISTS sync_history (
    sync_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_sha TEXT,
    target_sha TEXT,
    sync_type TEXT CHECK(sync_type IN ('to_original', 'from_original', 'merge')),
    
    timestamp REAL NOT NULL,
    success INTEGER NOT NULL,
    conflicts_json TEXT
);

CREATE TABLE IF NOT EXISTS workspace_info (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class MetadataManager:
    """
    Manages workspace metadata and state tracking.
    
    Uses SQLite for fast queries, Git refs for version history.
    """
    
    def __init__(self, registry_path: Path):
        """
        Initialize metadata manager.
        
        Args:
            registry_path: Path to global registry database.
        """
        self.registry_path = registry_path
        self._init_registry()
    
    def _init_registry(self) -> None:
        """Initialize registry database."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(self.registry_path))
        conn.executescript(REGISTRY_SCHEMA)
        
        # Insert default config if not exists
        conn.execute("""
            INSERT OR IGNORE INTO config (key, value, updated_at)
            VALUES ('version', '1.0', ?)
        """, (time.time(),))
        
        conn.commit()
        conn.close()
    
    # ===== Workspace Registry Operations =====
    
    def create_workspace(self, workspace: Workspace) -> None:
        """
        Register a new workspace in the registry.
        
        Args:
            workspace: Workspace to register.
        """
        conn = sqlite3.connect(str(self.registry_path))
        
        config_json = json.dumps({
            "auto_commit": workspace.config.auto_commit,
            "commit_prefix": workspace.config.commit_prefix,
            "sync_on_destroy": workspace.config.sync_on_destroy,
            "lock_after_create": workspace.config.lock_after_create,
            "hooks_enabled": workspace.config.hooks_enabled,
            "max_disk_usage_mb": workspace.config.max_disk_usage_mb,
        })
        
        conn.execute("""
            INSERT INTO workspaces (
                workspace_id, original_path, storage_path, workspace_dir,
                git_dir, copies_dir, metadata_db, workspace_type, status,
                created_at, last_accessed, created_by, git_mode, git_branch,
                git_head, config_json, backend_meta_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            workspace.workspace_id,
            workspace.original_path,
            workspace.storage_path,
            workspace.workspace_dir,
            workspace.git_dir,
            workspace.copies_dir,
            workspace.metadata_db,
            workspace.workspace_type.value,
            workspace.status.value,
            workspace.created_at.timestamp(),
            workspace.last_accessed.timestamp() if workspace.last_accessed else None,
            workspace.created_by,
            workspace.git_mode.value,
            workspace.git_branch,
            workspace.git_head,
            config_json,
            json.dumps(workspace.backend_meta),
        ))
        
        # Initialize stats
        conn.execute("""
            INSERT INTO workspace_stats (workspace_id, last_updated)
            VALUES (?, ?)
        """, (workspace.workspace_id, time.time()))
        
        conn.commit()
        conn.close()
        
        # Initialize per-workspace database
        self._init_workspace_db(Path(workspace.metadata_db))
    
    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """
        Get workspace by ID.
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            Workspace if found, None otherwise.
        """
        conn = sqlite3.connect(str(self.registry_path))
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute("""
            SELECT * FROM workspaces WHERE workspace_id = ?
        """, (workspace_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return self._row_to_workspace(row)
    
    def list_workspaces(
        self,
        status: Optional[WorkspaceStatus] = None,
        original_path: Optional[str] = None,
    ) -> list[Workspace]:
        """
        List all workspaces, optionally filtered.
        
        Args:
            status: Filter by status.
            original_path: Filter by original path.
        
        Returns:
            List of matching workspaces.
        """
        conn = sqlite3.connect(str(self.registry_path))
        conn.row_factory = sqlite3.Row
        
        query = "SELECT * FROM workspaces"
        params = []
        
        conditions = []
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if original_path:
            conditions.append("original_path = ?")
            params.append(original_path)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY created_at DESC"
        
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_workspace(row) for row in rows]
    
    def update_workspace(self, workspace: Workspace) -> None:
        """
        Update workspace in registry.
        
        Args:
            workspace: Workspace with updated fields.
        """
        conn = sqlite3.connect(str(self.registry_path))
        
        config_json = json.dumps({
            "auto_commit": workspace.config.auto_commit,
            "commit_prefix": workspace.config.commit_prefix,
            "sync_on_destroy": workspace.config.sync_on_destroy,
            "lock_after_create": workspace.config.lock_after_create,
            "hooks_enabled": workspace.config.hooks_enabled,
            "max_disk_usage_mb": workspace.config.max_disk_usage_mb,
        })
        
        conn.execute("""
            UPDATE workspaces SET
                status = ?,
                last_accessed = ?,
                git_mode = ?,
                git_branch = ?,
                git_head = ?,
                config_json = ?,
                backend_meta_json = ?
            WHERE workspace_id = ?
        """, (
            workspace.status.value,
            workspace.last_accessed.timestamp() if workspace.last_accessed else None,
            workspace.git_mode.value,
            workspace.git_branch,
            workspace.git_head,
            config_json,
            json.dumps(workspace.backend_meta),
            workspace.workspace_id,
        ))
        
        conn.commit()
        conn.close()
    
    def update_workspace_stats(
        self,
        workspace_id: str,
        total_files: int,
        linked_files: int,
        copied_files: int,
        new_files: int,
        deleted_files: int,
        disk_usage_bytes: int,
        original_size_bytes: int,
    ) -> None:
        """
        Update workspace statistics.
        
        Args:
            workspace_id: Workspace identifier.
            ...stats: Various stat values.
        """
        conn = sqlite3.connect(str(self.registry_path))
        
        savings_ratio = 1.0 - (disk_usage_bytes / original_size_bytes) if original_size_bytes > 0 else 0.0
        
        conn.execute("""
            UPDATE workspace_stats SET
                total_files = ?,
                linked_files = ?,
                copied_files = ?,
                new_files = ?,
                deleted_files = ?,
                disk_usage_bytes = ?,
                original_size_bytes = ?,
                savings_ratio = ?,
                last_updated = ?
            WHERE workspace_id = ?
        """, (
            total_files,
            linked_files,
            copied_files,
            new_files,
            deleted_files,
            disk_usage_bytes,
            original_size_bytes,
            savings_ratio,
            time.time(),
            workspace_id,
        ))
        
        conn.commit()
        conn.close()
    
    def delete_workspace(self, workspace_id: str) -> None:
        """
        Delete workspace from registry.
        
        Args:
            workspace_id: Workspace identifier.
        """
        conn = sqlite3.connect(str(self.registry_path))
        
        conn.execute("DELETE FROM workspace_stats WHERE workspace_id = ?", (workspace_id,))
        conn.execute("DELETE FROM workspace_history WHERE workspace_id = ?", (workspace_id,))
        conn.execute("DELETE FROM workspaces WHERE workspace_id = ?", (workspace_id,))
        
        conn.commit()
        conn.close()
    
    def record_history(
        self,
        workspace_id: str,
        operation: str,
        details: Optional[dict] = None,
    ) -> None:
        """
        Record workspace history event.
        
        Args:
            workspace_id: Workspace identifier.
            operation: Operation name.
            details: Optional details dictionary.
        """
        conn = sqlite3.connect(str(self.registry_path))
        
        conn.execute("""
            INSERT INTO workspace_history (workspace_id, operation, timestamp, details_json)
            VALUES (?, ?, ?, ?)
        """, (
            workspace_id,
            operation,
            time.time(),
            json.dumps(details) if details else None,
        ))
        
        conn.commit()
        conn.close()
    
    def _row_to_workspace(self, row: sqlite3.Row) -> Workspace:
        """Convert database row to Workspace."""
        config_data = json.loads(row["config_json"]) if row["config_json"] else {}
        
        return Workspace(
            workspace_id=row["workspace_id"],
            original_path=row["original_path"],
            storage_path=row["storage_path"],
            workspace_dir=row["workspace_dir"],
            git_dir=row["git_dir"],
            copies_dir=row["copies_dir"],
            metadata_db=row["metadata_db"],
            workspace_type=WorkspaceType(row["workspace_type"]),
            status=WorkspaceStatus(row["status"]),
            created_at=datetime.fromtimestamp(row["created_at"]),
            last_accessed=datetime.fromtimestamp(row["last_accessed"]) if row["last_accessed"] else None,
            created_by=row["created_by"],
            git_mode=GitMode(row["git_mode"]) if row["git_mode"] else GitMode.INHERITED,
            git_branch=row["git_branch"],
            git_head=row["git_head"],
            config=WorkspaceConfig(**config_data),
            backend_meta=json.loads(row["backend_meta_json"]) if row["backend_meta_json"] else {},
        )
    
    # ===== Per-Workspace Database Operations =====
    
    def _init_workspace_db(self, db_path: Path) -> None:
        """Initialize per-workspace database."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(db_path))
        conn.executescript(WORKSPACE_SCHEMA)
        conn.commit()
        conn.close()
    
    # File State Operations
    
    def record_linked_file(
        self,
        workspace_id: str,
        rel_path: str,
        original_hash: str,
        original_size: int,
        original_mtime: Optional[datetime] = None,
    ) -> None:
        """
        Record initial symlink state.
        
        Args:
            workspace_id: Workspace identifier.
            rel_path: Relative path of file.
            original_hash: Hash of original file.
            original_size: Size of original file.
            original_mtime: Modification time of original.
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return
        
        conn = sqlite3.connect(str(workspace.metadata_db))
        
        conn.execute("""
            INSERT OR REPLACE INTO file_state (
                relative_path, status, original_hash, original_size, original_mtime
            ) VALUES (?, 'linked', ?, ?, ?)
        """, (
            rel_path,
            original_hash,
            original_size,
            original_mtime.timestamp() if original_mtime else None,
        ))
        
        conn.commit()
        conn.close()
    
    def record_copy_up(
        self,
        workspace_id: str,
        rel_path: str,
        original_hash: str,
        original_size: int,
        cow_path: str,
        cow_hash: str,
        cow_size: int,
        cow_mtime: Optional[datetime] = None,
    ) -> None:
        """
        Record COW operation.
        
        Args:
            workspace_id: Workspace identifier.
            rel_path: Relative path of file.
            original_hash: Hash of original file.
            original_size: Size of original file.
            cow_path: Path to COW copy.
            cow_hash: Hash of COW copy.
            cow_size: Size of COW copy.
            cow_mtime: Modification time of COW.
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return
        
        conn = sqlite3.connect(str(workspace.metadata_db))
        now = time.time()
        
        conn.execute("""
            INSERT OR REPLACE INTO file_state (
                relative_path, status, original_hash, original_size,
                cow_path, cow_hash, cow_size, cow_mtime,
                first_modified_at, last_modified_at, modification_count
            ) VALUES (?, 'copied', ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            rel_path,
            original_hash,
            original_size,
            cow_path,
            cow_hash,
            cow_size,
            cow_mtime.timestamp() if cow_mtime else None,
            now,
            now,
        ))
        
        conn.commit()
        conn.close()
    
    def record_new_file(
        self,
        workspace_id: str,
        rel_path: str,
        cow_path: str,
        cow_hash: str,
        cow_size: int,
    ) -> None:
        """
        Record new file creation.
        
        Args:
            workspace_id: Workspace identifier.
            rel_path: Relative path of file.
            cow_path: Path to file in COW storage.
            cow_hash: Hash of file.
            cow_size: Size of file.
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return
        
        conn = sqlite3.connect(str(workspace.metadata_db))
        now = time.time()
        
        conn.execute("""
            INSERT INTO file_state (
                relative_path, status, cow_path, cow_hash, cow_size,
                first_modified_at, last_modified_at, modification_count
            ) VALUES (?, 'new', ?, ?, ?, ?, ?, 0)
        """, (
            rel_path,
            cow_path,
            cow_hash,
            cow_size,
            now,
            now,
        ))
        
        conn.commit()
        conn.close()
    
    def record_deletion(self, workspace_id: str, rel_path: str) -> None:
        """
        Record file deletion.
        
        Args:
            workspace_id: Workspace identifier.
            rel_path: Relative path of file.
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return
        
        conn = sqlite3.connect(str(workspace.metadata_db))
        
        conn.execute("""
            UPDATE file_state SET status = 'deleted' WHERE relative_path = ?
        """, (rel_path,))
        
        conn.commit()
        conn.close()
    
    def get_file_state(self, workspace_id: str, rel_path: str) -> Optional[FileState]:
        """
        Get file state.
        
        Args:
            workspace_id: Workspace identifier.
            rel_path: Relative path of file.
        
        Returns:
            FileState if found, None otherwise.
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return None
        
        conn = sqlite3.connect(str(workspace.metadata_db))
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute("""
            SELECT * FROM file_state WHERE relative_path = ?
        """, (rel_path,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return FileState(
            workspace_id=workspace_id,
            relative_path=row["relative_path"],
            status=FileStatus(row["status"]),
            original_hash=row["original_hash"],
            original_size=row["original_size"],
            original_mtime=datetime.fromtimestamp(row["original_mtime"]) if row["original_mtime"] else None,
            cow_path=row["cow_path"],
            cow_hash=row["cow_hash"],
            cow_size=row["cow_size"],
            cow_mtime=datetime.fromtimestamp(row["cow_mtime"]) if row["cow_mtime"] else None,
            first_modified_at=datetime.fromtimestamp(row["first_modified_at"]) if row["first_modified_at"] else None,
            last_modified_at=datetime.fromtimestamp(row["last_modified_at"]) if row["last_modified_at"] else None,
            modification_count=row["modification_count"] or 0,
            git_tracked=bool(row["git_tracked"]),
            git_blob_sha=row["git_blob_sha"],
            git_staged=bool(row["git_staged"]),
        )
    
    def list_file_states(
        self,
        workspace_id: str,
        status: Optional[FileStatus] = None,
    ) -> list[FileState]:
        """
        List all file states in workspace.
        
        Args:
            workspace_id: Workspace identifier.
            status: Optional status filter.
        
        Returns:
            List of FileState objects.
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return []
        
        conn = sqlite3.connect(str(workspace.metadata_db))
        conn.row_factory = sqlite3.Row
        
        if status:
            cursor = conn.execute("""
                SELECT * FROM file_state WHERE status = ?
            """, (status.value,))
        else:
            cursor = conn.execute("SELECT * FROM file_state")
        
        rows = cursor.fetchall()
        conn.close()
        
        states = []
        for row in rows:
            states.append(FileState(
                workspace_id=workspace_id,
                relative_path=row["relative_path"],
                status=FileStatus(row["status"]),
                original_hash=row["original_hash"],
                original_size=row["original_size"],
                original_mtime=datetime.fromtimestamp(row["original_mtime"]) if row["original_mtime"] else None,
                cow_path=row["cow_path"],
                cow_hash=row["cow_hash"],
                cow_size=row["cow_size"],
                cow_mtime=datetime.fromtimestamp(row["cow_mtime"]) if row["cow_mtime"] else None,
                first_modified_at=datetime.fromtimestamp(row["first_modified_at"]) if row["first_modified_at"] else None,
                last_modified_at=datetime.fromtimestamp(row["last_modified_at"]) if row["last_modified_at"] else None,
                modification_count=row["modification_count"] or 0,
                git_tracked=bool(row["git_tracked"]),
                git_blob_sha=row["git_blob_sha"],
                git_staged=bool(row["git_staged"]),
            ))
        
        return states
    
    # Git Commit Operations
    
    def record_commit(self, commit: GitCommit) -> None:
        """
        Record Git commit in workspace metadata.
        
        Args:
            commit: GitCommit to record.
        """
        workspace = self.get_workspace(commit.workspace_id)
        if not workspace:
            return
        
        conn = sqlite3.connect(str(workspace.metadata_db))
        
        conn.execute("""
            INSERT OR REPLACE INTO git_commits (
                commit_sha, commit_message, tree_sha, parent_sha,
                author_name, author_email, authored_at,
                committer_name, committer_email, committed_at,
                files_changed, insertions, deletions,
                commit_type, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            commit.commit_sha,
            commit.commit_message,
            commit.tree_sha,
            commit.parent_sha,
            commit.author_name,
            commit.author_email,
            commit.authored_at.timestamp() if commit.authored_at else None,
            commit.committer_name,
            commit.committer_email,
            commit.committed_at.timestamp() if commit.committed_at else None,
            commit.files_changed,
            commit.insertions,
            commit.deletions,
            commit.commit_type.value,
            commit.metadata_json,
        ))
        
        conn.commit()
        conn.close()
    
    def list_commits(self, workspace_id: str) -> list[GitCommit]:
        """
        List all commits for workspace.
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            List of GitCommit objects.
        """
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return []
        
        conn = sqlite3.connect(str(workspace.metadata_db))
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute("""
            SELECT * FROM git_commits ORDER BY committed_at DESC
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        commits = []
        for row in rows:
            commits.append(GitCommit(
                workspace_id=workspace_id,
                commit_sha=row["commit_sha"],
                commit_message=row["commit_message"],
                tree_sha=row["tree_sha"],
                parent_sha=row["parent_sha"],
                author_name=row["author_name"],
                author_email=row["author_email"],
                authored_at=datetime.fromtimestamp(row["authored_at"]) if row["authored_at"] else None,
                committer_name=row["committer_name"],
                committer_email=row["committer_email"],
                committed_at=datetime.fromtimestamp(row["committed_at"]) if row["committed_at"] else None,
                files_changed=row["files_changed"] or 0,
                insertions=row["insertions"] or 0,
                deletions=row["deletions"] or 0,
                commit_type=CommitType(row["commit_type"] or "user"),
                metadata_json=row["metadata_json"],
            ))
        
        return commits
    
    # Operations Log
    
    def log_operation(self, log_entry: OperationLog) -> int:
        """
        Log an operation.
        
        Args:
            log_entry: OperationLog to record.
        
        Returns:
            Operation ID.
        """
        workspace = self.get_workspace(log_entry.workspace_id)
        if not workspace:
            return -1
        
        conn = sqlite3.connect(str(workspace.metadata_db))
        
        cursor = conn.execute("""
            INSERT INTO operations_log (
                operation_type, relative_path, timestamp, duration_ms,
                success, error_message, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            log_entry.operation_type.value,
            log_entry.relative_path,
            log_entry.timestamp.timestamp(),
            log_entry.duration_ms,
            1 if log_entry.success else 0,
            log_entry.error_message,
            log_entry.details_json,
        ))
        
        operation_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return operation_id if operation_id else -1