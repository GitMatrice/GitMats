# GitMats Data Model

## Overview

This document defines the data structures, schemas, and state management for GitMats virtual workspace system.

## Core Entities

### 1. Workspace

```python
@dataclass
class Workspace:
    """
    Virtual workspace entity.
    
    A workspace represents an isolated working environment
    that shares files with an original directory via COW.
    """
    
    # Identity
    workspace_id: str              # Unique identifier (e.g., 'user123')
    
    # Paths
    original_path: str             # Original workspace (read-only)
    storage_path: str              # ~/.gitmats/workspaces/{id}
    workspace_dir: str             # storage/workspace (working directory)
    git_dir: str                   # storage/git (Git metadata)
    copies_dir: str                # storage/copies (COW files)
    metadata_db: str               # storage/metadata.db
    
    # Type
    workspace_type: WorkspaceType  # INHERITED or STANDALONE
    
    # State
    status: WorkspaceStatus        # ACTIVE, LOCKED, DESTROYED
    created_at: datetime
    last_accessed: datetime
    created_by: str                # User/session ID
    
    # Git Integration
    git_mode: GitMode              # INHERITED or STANDALONE
    git_branch: str                # Current branch
    git_head: str                  # Current commit SHA
    
    # Statistics (cached)
    total_files: int
    linked_files: int
    copied_files: int
    new_files: int
    deleted_files: int
    disk_usage_bytes: int
    
    # Configuration
    config: WorkspaceConfig


enum WorkspaceType:
    INHERITED = 'inherited'        # Original has Git
    STANDALONE = 'standalone'      # Original has no Git


enum WorkspaceStatus:
    ACTIVE = 'active'
    LOCKED = 'locked'
    DESTROYED = 'destroyed'
    ARCHIVED = 'archived'


enum GitMode:
    INHERITED = 'inherited'        # Share Git with original (worktree)
    STANDALONE = 'standalone'      # Independent Git repo


@dataclass
class WorkspaceConfig:
    """Per-workspace configuration."""
    
    auto_commit: bool = False
    commit_prefix: str = ""
    sync_on_destroy: bool = False
    lock_after_create: bool = False
    hooks_enabled: bool = True
    max_disk_usage_mb: int = None  # Optional limit
```

### 2. FileState

```python
@dataclass
class FileState:
    """
    State tracking for a file in workspace.
    
    Tracks whether file is:
    - Linked to original (unchanged)
    - Copied to COW layer (modified)
    - New (created in workspace)
    - Deleted (removed from workspace)
    """
    
    # Identity
    workspace_id: str
    relative_path: str             # Path relative to workspace root
    
    # State
    status: FileStatus             # LINKED, COPIED, NEW, DELETED
    
    # Original (if linked or copied)
    original_hash: str             # SHA-256 hash
    original_size: int             # Bytes
    original_mtime: datetime       # Last modified in original
    
    # COW Copy (if copied or new)
    cow_path: str                  # Absolute path to COW copy
    cow_hash: str                  # SHA-256 hash
    cow_size: int                  # Bytes
    cow_mtime: datetime            # Last modified in COW
    
    # Modification tracking
    first_modified_at: datetime    # When first copied/created
    last_modified_at: datetime     # Last modification time
    modification_count: int        # Number of modifications
    
    # Git integration
    git_tracked: bool = True
    git_blob_sha: str = None       # Git blob hash
    git_staged: bool = False


enum FileStatus:
    LINKED = 'linked'              # Symlink to original (unchanged)
    COPIED = 'copied'              # Symlink to COW copy (modified)
    NEW = 'new'                    # Created in workspace (no original)
    DELETED = 'deleted'            # Removed from workspace
    UNKNOWN = 'unknown'            # Not tracked
```

### 3. GitCommit

```python
@dataclass
class GitCommit:
    """
    Git commit metadata tracked by GitMats.
    
    Links Git commits to workspace state.
    """
    
    # Identity
    workspace_id: str
    commit_sha: str                # Git commit hash
    
    # Content
    commit_message: str
    tree_sha: str                  # Git tree hash
    parent_sha: str                # Parent commit (or None for root)
    
    # Author
    author_name: str
    author_email: str
    authored_at: datetime
    
    # Committer
    committer_name: str
    committer_email: str
    committed_at: datetime
    
    # Statistics
    files_changed: int
    insertions: int
    deletions: int
    
    # GitMats metadata
    commit_type: CommitType        # USER, COW_SYNC, BASE, SYNC
    metadata_json: str             # Additional metadata as JSON


enum CommitType:
    USER = 'user'                  # User-initiated commit
    COW_SYNC = 'cow_sync'          # Automatic COW sync
    BASE = 'base'                  # Virtual base commit (standalone)
    SYNC = 'sync'                  # Sync to original commit
```

### 4. OperationLog

```python
@dataclass
class OperationLog:
    """
    Log of all operations in workspace.
    
    Provides audit trail and debugging info.
    """
    
    # Identity
    workspace_id: str
    operation_id: int              # Auto-increment
    
    # Operation
    operation_type: OperationType
    relative_path: str             # Affected file (if applicable)
    
    # Timing
    timestamp: datetime
    duration_ms: int               # Operation duration
    
    # Result
    success: bool
    error_message: str             # If failed
    
    # Details
    details_json: str              # Operation-specific details


enum OperationType:
    # Workspace operations
    CREATE_WORKSPACE = 'create_workspace'
    DESTROY_WORKSPACE = 'destroy_workspace'
    LOCK_WORKSPACE = 'lock_workspace'
    
    # File operations
    COPY_UP = 'copy_up'
    CREATE_FILE = 'create_file'
    DELETE_FILE = 'delete_file'
    RESET_FILE = 'reset_file'
    
    # Git operations
    GIT_ADD = 'git_add'
    GIT_COMMIT = 'git_commit'
    GIT_BRANCH = 'git_branch'
    GIT_SYNC = 'git_sync'
    
    # Metadata operations
    METADATA_UPDATE = 'metadata_update'
    VALIDATE = 'validate'
```

## Database Schemas

### Global Registry Database

```sql
-- ~/.gitmats/registry.db
-- Tracks all workspaces globally

CREATE TABLE workspaces (
    workspace_id TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    workspace_type TEXT NOT NULL CHECK(workspace_type IN ('inherited', 'standalone')),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'locked', 'destroyed', 'archived')),
    created_at REAL NOT NULL,
    last_accessed REAL,
    created_by TEXT,
    git_mode TEXT CHECK(git_mode IN ('inherited', 'standalone')),
    git_branch TEXT,
    git_head TEXT,
    config_json TEXT,              -- JSON-encoded WorkspaceConfig
    
    -- Indexes
    UNIQUE(workspace_id),
    INDEX(original_path),
    INDEX(status),
    INDEX(created_at)
);

CREATE TABLE workspace_stats (
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

CREATE TABLE workspace_history (
    workspace_id TEXT,
    operation TEXT NOT NULL,
    timestamp REAL NOT NULL,
    details_json TEXT,
    
    FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    INDEX(workspace_id, timestamp)
);

-- Configuration
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL
);

INSERT INTO config VALUES ('version', '1.0', NULL);
INSERT INTO config VALUES ('default_workspace_dir', '~/.gitmats/workspaces', NULL);
```

### Per-Workspace Metadata Database

```sql
-- ~/.gitmats/workspaces/{id}/metadata.db
-- Detailed tracking for single workspace

CREATE TABLE file_state (
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
    git_staged INTEGER DEFAULT 0,
    
    -- Indexes
    INDEX(status),
    INDEX(git_staged)
);

CREATE TABLE git_commits (
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
    metadata_json TEXT,
    
    -- Indexes
    INDEX(committed_at),
    INDEX(commit_type)
);

CREATE TABLE git_refs (
    ref_name TEXT PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    created_at REAL,
    updated_at REAL,
    
    FOREIGN KEY(commit_sha) REFERENCES git_commits(commit_sha)
);

CREATE TABLE operations_log (
    operation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type TEXT NOT NULL,
    relative_path TEXT,
    
    timestamp REAL NOT NULL,
    duration_ms INTEGER,
    
    success INTEGER NOT NULL,
    error_message TEXT,
    
    details_json TEXT,
    
    -- Indexes
    INDEX(timestamp),
    INDEX(operation_type),
    INDEX(relative_path)
);

CREATE TABLE sync_history (
    sync_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_sha TEXT,
    target_sha TEXT,
    sync_type TEXT CHECK(sync_type IN ('to_original', 'from_original', 'merge')),
    
    timestamp REAL NOT NULL,
    success INTEGER NOT NULL,
    conflicts_json TEXT,           -- List of conflicting files
    
    FOREIGN KEY(source_sha) REFERENCES git_commits(commit_sha),
    FOREIGN KEY(target_sha) REFERENCES git_commits(commit_sha)
);

-- Workspace info (mirror of registry for quick access)
CREATE TABLE workspace_info (
    key TEXT PRIMARY KEY,
    value TEXT
);

INSERT INTO workspace_info VALUES ('workspace_id', ?);
INSERT INTO workspace_info VALUES ('original_path', ?);
INSERT INTO workspace_info VALUES ('workspace_type', ?);
INSERT INTO workspace_info VALUES ('git_mode', ?);
```

## Git Refs Schema

### Inherited Mode Refs

```
# In original repository's .git/refs/

refs/
├── heads/
│   └── main                      # Original main branch
│
├── gitmats/                      # GitMats tracking refs
│   └── {workspace_id}/
│       ├── base                  # SHA at workspace creation
│       ├── last-sync             # Last sync point
│       └── workspace-head        # Current workspace HEAD
│
└── remotes/
    └── origin/

# In workspace's .git/refs/

refs/
├── heads/
│   └── workspace-{id}-main       # Workspace working branch
│
└── worktree/
    └── {workspace_id}            # Worktree metadata ref
```

### Standalone Mode Refs

```
# In workspace's git/refs/ (independent repo)

refs/
├── heads/
│   └── main                      # Main branch (workspace history)
│
├── gitmats/                      # GitMats tracking refs
│   ├── base                      # Virtual base commit (root)
│   ├── cow-head                  # Current COW state
│   └── last-sync                 # Last sync (if synced to external)
│
└── remotes/                      # Optional remote refs
    └── origin/
```

## State Transitions

### Workspace State Transitions

```
┌───────────────────────────────────────────────────────────────┐
│                 Workspace Lifecycle                            │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│   [None]                                                       │
│      │                                                         │
│      │ create                                                  │
│      ▼                                                         │
│   ┌─────────┐                                                  │
│   │ ACTIVE  │◄──────────────┐                                 │
│   └─────────┘                │ unlock                          │
│      │                       │                                 │
│      ├──────►┌─────────┐─────┘                                 │
│      │ lock  │ LOCKED  │                                       │
│      │       └─────────┘                                       │
│      │            │                                            │
│      │            │ destroy                                    │
│      │            ▼                                            │
│      ├──────►┌──────────┐                                      │
│      │       │ DESTROYED│                                      │
│      │       └──────────┘                                      │
│      │            │                                            │
│      │            │ archive                                    │
│      │            ▼                                            │
│      └──────►┌──────────┐                                      │
│              │ ARCHIVED │                                      │
│              └──────────┘                                      │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

### File State Transitions

```
┌───────────────────────────────────────────────────────────────┐
│                   File Lifecycle                               │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│   [Original File]                                              │
│      │                                                         │
│      │ create workspace (symlink)                              │
│      ▼                                                         │
│   ┌─────────┐                                                  │
│   │ LINKED  │◄──────────────────┐                             │
│   └─────────┘                   │ reset                        │
│      │                          │                              │
│      ├──────►┌─────────┐────────┘                              │
│      │ copy  │ COPIED  │                                       │
│      │       └─────────┘                                       │
│      │            │                                            │
│      │            │ modify (stays COPIED)                      │
│      │            │                                            │
│      ├──────►┌──────────┐                                      │
│      │ delete│ DELETED  │                                      │
│      │       └──────────┘                                      │
│                                                                │
│   [No Original File]                                           │
│      │                                                         │
│      │ create in workspace                                     │
│      ▼                                                         │
│   ┌─────────┐                                                  │
│   │   NEW   │                                                  │
│   └─────────┘                                                  │
│      │                                                         │
│      │ delete                                                  │
│      ▼                                                         │
│   [Removed from tracking]                                      │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

## Data Access Patterns

### Common Queries

```python
class WorkspaceQueries:
    """
    Common database queries for workspace management.
    """
    
    # Get workspace by ID
    GET_WORKSPACE = """
        SELECT * FROM workspaces WHERE workspace_id = ?
    """
    
    # List all active workspaces
    LIST_ACTIVE = """
        SELECT w.*, s.*
        FROM workspaces w
        LEFT JOIN workspace_stats s ON w.workspace_id = s.workspace_id
        WHERE w.status = 'active'
        ORDER BY w.last_accessed DESC
    """
    
    # Get file state
    GET_FILE_STATE = """
        SELECT * FROM file_state WHERE relative_path = ?
    """
    
    # List all modified files
    LIST_MODIFIED = """
        SELECT relative_path, status, original_size, cow_size
        FROM file_state
        WHERE status IN ('copied', 'new')
        ORDER BY last_modified_at DESC
    """
    
    # Calculate disk usage
    DISK_USAGE = """
        SELECT 
            SUM(COALESCE(cow_size, 0)) as cow_bytes,
            SUM(COALESCE(original_size, 0)) as original_bytes,
            COUNT(*) as total_files,
            SUM(CASE WHEN status='linked' THEN 1 ELSE 0 END) as linked,
            SUM(CASE WHEN status='copied' THEN 1 ELSE 0 END) as copied,
            SUM(CASE WHEN status='new' THEN 1 ELSE 0 END) as new,
            SUM(CASE WHEN status='deleted' THEN 1 ELSE 0 END) as deleted
        FROM file_state
    """
    
    # Get recent commits
    RECENT_COMMITS = """
        SELECT * FROM git_commits
        ORDER BY committed_at DESC
        LIMIT 10
    """
    
    # Get operations log
    OPERATIONS_LOG = """
        SELECT * FROM operations_log
        WHERE timestamp > ?
        ORDER BY timestamp DESC
    """
```

## Caching Strategy

### In-Memory Cache

```python
class WorkspaceCache:
    """
    Cache frequently accessed workspace data.
    
    LRU cache with TTL for automatic invalidation.
    """
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl_seconds
        
    def get_workspace(self, workspace_id: str) -> Workspace | None:
        """Get cached workspace metadata."""
        
        key = f"workspace:{workspace_id}"
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry.timestamp < self.ttl:
                self.cache.move_to_end(key)  # LRU update
                return entry.data
            else:
                del self.cache[key]  # TTL expired
        
        return None
    
    def cache_workspace(self, workspace: Workspace) -> None:
        """Cache workspace metadata."""
        
        key = f"workspace:{workspace.workspace_id}"
        self.cache[key] = CacheEntry(
            data=workspace,
            timestamp=time.time()
        )
        
        # Evict if over limit
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)
    
    def invalidate(self, workspace_id: str) -> None:
        """Invalidate workspace cache."""
        
        key = f"workspace:{workspace_id}"
        if key in self.cache:
            del self.cache[key]
```

### File State Cache

```python
class FileStateCache:
    """
    Cache file states for quick resolution.
    
    Separate cache per workspace.
    """
    
    def __init__(self):
        self.caches = {}  # workspace_id -> OrderedDict
    
    def get_file_state(self, workspace_id: str, 
                       rel_path: str) -> FileState | None:
        """Get cached file state."""
        
        if workspace_id not in self.caches:
            return None
        
        cache = self.caches[workspace_id]
        key = rel_path
        
        if key in cache:
            return cache[key]
        
        return None
    
    def cache_file_state(self, workspace_id: str,
                         state: FileState) -> None:
        """Cache file state."""
        
        if workspace_id not in self.caches:
            self.caches[workspace_id] = OrderedDict()
        
        cache = self.caches[workspace_id]
        cache[state.relative_path] = state
        
        # Limit per-workspace cache size
        if len(cache) > 1000:
            cache.popitem(last=False)
```

## Data Consistency

### Integrity Checks

```python
class DataValidator:
    """
    Validate data consistency across GitMats components.
    """
    
    def validate_workspace(self, workspace: Workspace) -> ValidationResult:
        """
        Validate workspace integrity.
        
        Checks:
        1. All paths exist
        2. Metadata database accessible
        3. Git refs valid
        4. File states consistent with actual files
        """
        
        errors = []
        
        # Check paths
        if not Path(workspace.original_path).exists():
            errors.append(f"Original path missing: {workspace.original_path}")
        
        if not Path(workspace.workspace_dir).exists():
            errors.append(f"Workspace directory missing: {workspace.workspace_dir}")
        
        # Check metadata
        if not Path(workspace.metadata_db).exists():
            errors.append(f"Metadata database missing: {workspace.metadata_db}")
        
        # Check Git
        if workspace.git_mode == 'inherited':
            if not self.validate_git_refs(workspace.git_dir):
                errors.append("Git refs invalid")
        
        # Check file states
        inconsistent_files = self.validate_file_states(workspace)
        if inconsistent_files:
            errors.append(f"Inconsistent file states: {len(inconsistent_files)} files")
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            inconsistent_files=inconsistent_files
        )
    
    def validate_file_states(self, workspace: Workspace) -> list[str]:
        """
        Validate file states match actual files.
        
        For each tracked file:
        - If 'linked': workspace symlink should point to original
        - If 'copied': workspace symlink should point to COW copy
        - If 'new': workspace file should exist (symlink to COW)
        - If 'deleted': workspace file should NOT exist
        """
        
        inconsistent = []
        
        conn = sqlite3.connect(workspace.metadata_db)
        cursor = conn.execute("SELECT relative_path, status FROM file_state")
        
        for rel_path, status in cursor:
            workspace_path = Path(workspace.workspace_dir) / rel_path
            
            if status == 'linked':
                target = Path(workspace.original_path) / rel_path
                if not workspace_path.is_symlink():
                    inconsistent.append(rel_path)
                elif workspace_path.resolve() != target.resolve():
                    inconsistent.append(rel_path)
            
            elif status == 'copied':
                target = Path(workspace.copies_dir) / rel_path
                if not workspace_path.is_symlink():
                    inconsistent.append(rel_path)
                elif workspace_path.resolve() != target.resolve():
                    inconsistent.append(rel_path)
            
            elif status == 'new':
                if not workspace_path.exists():
                    inconsistent.append(rel_path)
            
            elif status == 'deleted':
                if workspace_path.exists():
                    inconsistent.append(rel_path)
        
        conn.close()
        return inconsistent
```

## Backup and Recovery

### Backup Strategy

```python
class BackupManager:
    """
    Backup workspace data for recovery.
    """
    
    def create_backup(self, workspace: Workspace) -> BackupResult:
        """
        Create backup of workspace.
        
        Includes:
        1. Metadata database
        2. Git refs
        3. COW copies (optional)
        4. Configuration
        
        Backup format: tar.gz archive
        """
        
        backup_path = Path(workspace.storage_path) / 'backups' / f'backup-{timestamp}.tar.gz'
        
        with tarfile.open(backup_path, 'w:gz') as tar:
            # Metadata
            tar.add(workspace.metadata_db, arcname='metadata.db')
            
            # Git refs
            git_refs = Path(workspace.git_dir) / 'refs'
            tar.add(git_refs, arcname='git/refs')
            
            # Config
            config_path = Path(workspace.storage_path) / '.gitmats.yaml'
            if config_path.exists():
                tar.add(config_path, arcname='.gitmats.yaml')
            
            # COW copies (optional)
            if self.include_copies:
                cow_dir = Path(workspace.copies_dir)
                tar.add(cow_dir, arcname='copies')
        
        return BackupResult(path=backup_path, size=backup_path.stat().st_size)
    
    def restore_backup(self, workspace_id: str,
                       backup_path: str) -> Workspace:
        """
        Restore workspace from backup.
        
        Warning: Overwrites existing workspace data.
        """
        
        storage_path = Path(f"~/.gitmats/workspaces/{workspace_id}").expanduser()
        
        with tarfile.open(backup_path, 'r:gz') as tar:
            tar.extractall(storage_path)
        
        # Reload workspace from restored metadata
        return self.load_workspace(workspace_id)
```

## Summary Statistics

```python
@dataclass
class WorkspaceSummary:
    """
    Summary statistics for a workspace.
    """
    
    workspace_id: str
    
    # File counts
    total_files: int
    linked_files: int              # Still symlinked to original
    copied_files: int              # COW copies
    new_files: int                 # Created in workspace
    deleted_files: int             # Deleted
    
    # Disk usage
    disk_usage_bytes: int          # Actual disk used by COW
    original_size_bytes: int       # Size if full copy
    savings_bytes: int             # Disk saved
    savings_percent: float         # Percentage saved
    
    # Git statistics
    commit_count: int              # Total commits
    last_commit_sha: str           # Latest commit
    last_commit_time: datetime
    
    # Activity
    created_at: datetime
    last_accessed: datetime
    last_modified: datetime
    operation_count: int           # Total operations logged
    
    def calculate_savings(self):
        """Calculate disk savings."""
        
        self.savings_bytes = self.original_size_bytes - self.disk_usage_bytes
        self.savings_percent = (
            (self.savings_bytes / self.original_size_bytes * 100)
            if self.original_size_bytes > 0 else 0
        )
```