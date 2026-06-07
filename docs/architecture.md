# GitMats Architecture

This document describes the system architecture and internal components of GitMats.

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                            GitMats System                              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │                           GMT CLI Interface                       ││
│  │                                                                   ││
│  │   $ gmt create <workspace-id> [--from=<original>]                ││
│  │   $ gmt list                                                      ││
│  │   $ gmt status <workspace-id>                                     ││
│  │   $ gmt commit <workspace-id> -m "message"                        ││
│  │   $ gmt destroy <workspace-id>                                    ││
│  │   $ gmt diff <workspace-id>                                       ││
│  │   $ gmt sync <workspace-id> [--to=<original>]                     ││
│  └──────────────────────────────────────────────────────────────────┘│
│                              │                                         │
│                              ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │                       Workspace Manager                           ││
│  │                                                                   ││
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ││
│  │  │ Workspace   │ │ Git Engine  │ │ COW Engine  │ │ Metadata    │ ││
│  │  │ Factory     │ │             │ │             │ │ Manager     │ ││
│  │  │             │ │ - worktree  │ │ - symlink   │ │ - SQLite    │ ││
│  │  │ - create    │ │ - alternates│ │   mgmt      │ │ - state     │ ││
│  │  │ - destroy   │ │ - refs      │ │ - copy_up   │ │   tracking  │ ││
│  │  │ - lifecycle │ │ - index     │ │ - tracking  │ │             │ ││
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ ││
│  └──────────────────────────────────────────────────────────────────┘│
│                              │                                         │
│            ┌─────────────────┴─────────────────┐                      │
│            │                                   │                      │
│            ▼                                   ▼                      │
│  ┌──────────────────────┐       ┌────────────────────────────────────┐│
│  │   Original Workspace │       │   Virtual Workspace Storage        ││
│  │   (Read-Only Base)   │       │                                    ││
│  │                      │       │   ~/.gitmats/                      ││
│  │   /original/         │       │   ├── workspaces/                 ││
│  │   ├── .git/          │◄──────│   │   ├── user123/                ││
│  │   │   ├── objects/   │ alt   │   │   │   ├── workspace/          ││
│  │   │   ├── refs/      │ obj   │   │   │   ├── git/                ││
│  │   │   └── worktrees/ │       │   │   │   ├── copies/             ││
│  │   ├── src/           │ symlink│   │   │   └── metadata.db        ││
│  │   ├── images/        │──────►│   │   └── user456/                ││
│  │   └── config.yaml    │       │   │       └── ...                 ││
│  │                      │       │   ├── registry.db                 ││
│  │                      │       │   └── templates/                  ││
│  └──────────────────────┘       └────────────────────────────────────┘│
│                                                                        │
└──────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. CLI Layer (gmt)

The CLI provides workspace management commands that follow Git conventions:

```bash
# Standard Git commands still work in virtual workspace
cd ~/.gitmats/workspaces/user123/workspace
git status              # Shows uncommitted COW changes
git add -A
git commit -m "changes"
git log                 # Shows commits in this workspace

# GMT provides workspace-level operations
gmt create user123 --from=/original
gmt status user123
gmt commit user123 -m "checkpoint"
gmt diff user123 --vs-original
gmt destroy user123
```

### 2. Workspace Manager

The central orchestration component that coordinates all workspace operations:

```python
class WorkspaceManager:
    """
    Central manager for all virtual workspaces.
    
    Responsibilities:
    - Workspace creation and destruction
    - Git integration setup
    - COW engine initialization
    - Metadata persistence
    """
    
    def create_workspace(self, workspace_id: str, 
                         original_path: str,
                         workspace_type: str = 'auto') -> Workspace:
        """
        Create a new virtual workspace.
        
        Process:
        1. Validate workspace ID and original path
        2. Detect workspace type (inherited vs standalone)
        3. Create directory structure
        4. Initialize Git (if applicable)
        5. Create COW symlinks
        6. Initialize metadata database
        7. Register in global registry
        """
        
    def detect_workspace_type(self, original_path: str) -> str:
        """Detect if original has Git repository"""
        git_dir = Path(original_path) / '.git'
        if git_dir.exists():
            return 'inherited'
        return 'standalone'
```

### 3. Git Engine

Handles all Git-related operations for version control:

```python
class LocalGitBackend:
    """
    Git integration for virtual workspaces.
    
    Two modes:
    - Inherited: Share objects with original, use worktree structure
    - Standalone: Independent git repository tracking COW changes
    """
    
    # ===== Inherited Mode (Original has Git) =====
    
    def setup_inherited_git(self, workspace: Workspace) -> None:
        """
        Setup Git for inherited workspace.
        
        Strategy: Git worktree + alternates
        
        1. Create linked worktree entry in original's .git/worktrees/
        2. Create workspace-specific:
           - HEAD (pointing to original HEAD or new branch)
           - index (staging area)
           - config.worktree (per-worktree config)
        3. Share object database with original (alternates)
        4. Create git-mats/* refs for tracking COW state
        """
        
    def create_virtual_worktree(self, original_git_dir: Path,
                                 workspace_id: str,
                                 worktree_path: Path) -> GitWorktree:
        """
        Create a virtual worktree entry.
        
        Structure:
        original/.git/worktrees/gitmats-{workspace_id}/
            ├── gitdir       -> points to workspace git dir
            ├── HEAD         -> workspace HEAD (branch)
            ├── index        -> workspace index file
            ├── config.worktree -> per-worktree config
            └── commondir    -> link to original commondir
        """
        
    # ===== Standalone Mode (Original has no Git) =====
    
    def setup_standalone_git(self, workspace: Workspace) -> None:
        """
        Setup independent Git repository for non-versioned original.
        
        Strategy: Create git in workspace storage, never touch original
        
        1. Initialize git repo in ~/.gitmats/workspaces/{id}/git/
        2. Create initial commit from symlink structure (virtual snapshot)
        3. Track all COW modifications as commits
        """
```

### 4. COW Engine

The Copy-on-Write engine manages file symlinks and lazy copying:

```python
class COWEngine:
    """
    Manages copy-on-write operations for files.
    
    Responsibilities:
    - Detect write operations
    - Copy files to COW layer
    - Update symlinks
    - Track modifications in metadata
    - Integrate with Git for versioning
    """
    
    def copy_up(self, workspace: Workspace, 
                rel_path: str, 
                content: bytes | None = None) -> Path:
        """
        Execute copy-on-write for a file.
        
        Steps:
        1. Check if already copied (skip if yes)
        2. Create COW directory structure
        3. Copy file from original to COW storage
        4. Remove existing symlink in workspace
        5. Create new symlink to COW copy
        6. Update metadata (mark as 'copied')
        7. Trigger git update if configured
        
        Returns:
            Path to the COW copy
        """
        
    def get_file_source(self, workspace: Workspace,
                        rel_path: str) -> FileSource:
        """
        Determine where file content comes from.
        
        Returns:
            FileSource enum:
            - ORIGINAL: symlink points to original (unchanged)
            - COW_COPY: symlink points to COW copy (modified)
            - NEW: file created in workspace (no original)
            - DELETED: file was deleted in workspace
        """
```

### 5. Metadata Manager

State tracking and persistence using SQLite:

```python
class MetadataManager:
    """
    Manages workspace metadata and state tracking.
    
    Uses SQLite for fast queries, Git refs for version history.
    """
    
    # Workspace Registry (global)
    schema_registry = """
        CREATE TABLE workspaces (
            workspace_id TEXT PRIMARY KEY,
            original_path TEXT NOT NULL,
            workspace_type TEXT NOT NULL,
            created_at REAL,
            last_accessed REAL,
            status TEXT DEFAULT 'active',
            git_mode TEXT  -- 'inherited' or 'standalone'
        );
        
        CREATE TABLE workspace_stats (
            workspace_id TEXT PRIMARY KEY,
            total_files INTEGER,
            copied_files INTEGER,
            new_files INTEGER,
            deleted_files INTEGER,
            disk_usage_bytes INTEGER,
            FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
        );
    """
    
    # Per-Workspace Metadata
    schema_workspace = """
        CREATE TABLE file_state (
            relative_path TEXT PRIMARY KEY,
            state TEXT NOT NULL,  -- 'linked', 'copied', 'new', 'deleted'
            original_hash TEXT,
            original_size INTEGER,
            cow_path TEXT,
            cow_hash TEXT,
            cow_size INTEGER,
            first_modified_at REAL,
            last_modified_at REAL,
            git_tracked BOOLEAN DEFAULT TRUE
        );
        
        CREATE TABLE operations_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            operation TEXT,  -- 'copy_up', 'create', 'delete', 'git_commit'
            relative_path TEXT,
            details_json TEXT
        );
    """
```

## Directory Structure

### Original Workspace (Read-Only)

```
/original/
├── .git/                          # Git repository (if exists)
│   ├── objects/                   # Object database (shared)
│   ├── refs/                      # References
│   ├── worktrees/                 # Linked worktrees
│   │   └── gitmats-{id}/          # GitMats worktree entries
│   │       ├── gitdir             # Points to workspace git
│   │       ├── HEAD               # Workspace HEAD
│   │       ├── index              # Workspace staging
│   │       └── commondir          # Shared common dir
│   └── config                     # Shared config
├── src/
│   ├── main.py                    # Symlinked to virtual
│   └── utils.py
├── images/
│   └── logo.png
└── config.yaml
```

### Virtual Workspace Storage

```
~/.gitmats/
├── registry.db                    # Global registry
├── config.yaml                    # GitMats configuration
├── templates/
│   └── workspace/                 # Template for new workspaces
│       └── .gitmats.yaml
└
└── workspaces/
    ├── user123/
    │   ├── workspace/             # Virtual working directory
    │   │   ├── src/
    │   │   │   ├── main.py        # -> symlink to original OR cow copy
    │   │   │   └── utils.py
    │   │   ├── images/
    │   │   │   └── logo.png       # -> symlink to original
    │   │   ├── config.yaml        # -> symlink to cow copy (modified)
    │   │   └── .git               # -> ../git (inherited) or ../git (standalone)
    │   │
    │   ├── git/                   # Git metadata for this workspace
    │   │   ├── HEAD               # Current branch/commit
    │   │   ├── index              # Staging area
    │   │   ├── config.worktree    # Per-worktree config
    │   │   ├── objects/           # COW objects (standalone only)
    │   │   │   └── pack/
    │   │   ├── refs/
    │   │   │   └── gitmats/
    │   │   │       ├── user123/
    │   │   │       │   ├── base       # Original HEAD at creation
    │   │   │       │   ├── cow-base   # Last sync point
    │   │   │       │   └── head       # Current state
    │   │   │       └── heads/
    │   │   │           └── main       # Workspace branch
    │   │   └── alternates          # Link to original objects (inherited)
    │   │
    │   ├── copies/                # COW file copies
    │   │   ├── src/
    │   │   │   └── main.py        # Modified copy
    │   │   └── config.yaml        # Modified copy
    │   │
    │   ├── metadata.db            # Workspace-specific metadata
    │   └── .gitmats.yaml          # Workspace config
    │
    └── user456/
        └── ...                    # Same structure
```

## File Resolution Logic

When accessing a file in virtual workspace:

```python
def resolve_file_path(workspace: Workspace, rel_path: str) -> Path:
    """
    Resolve actual file path for a virtual workspace file.
    
    Resolution order:
    1. Check metadata for file state
    2. If 'copied' or 'new': return COW copy path
    3. If 'linked': return original path
    4. If 'deleted': raise FileNotFoundError
    """
    
    state = metadata.get_file_state(workspace.id, rel_path)
    
    if state.status == 'copied':
        return workspace.copies_dir / rel_path
    elif state.status == 'new':
        return workspace.copies_dir / rel_path
    elif state.status == 'linked':
        return workspace.original_path / rel_path
    elif state.status == 'deleted':
        raise FileNotFoundError(f"File deleted in workspace: {rel_path}")
    
    # Default: linked to original
    return workspace.original_path / rel_path
```

## Symlink States

```
┌──────────────────────────────────────────────────────────────────┐
│                    Symlink States                                 │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  State: LINKED (initial)                                          │
│  ┌──────────────────┐                                            │
│  │ workspace/file   │──► /original/file                          │
│  └──────────────────┘                                            │
│  Disk: 0 bytes (symlink only)                                    │
│                                                                   │
│  State: COPIED (after modification)                              │
│  ┌──────────────────┐                                            │
│  │ workspace/file   │──► ~/.gitmats/wsid/copies/file             │
│  └──────────────────┘                                            │
│  Disk: actual file size in copies/                               │
│                                                                   │
│  State: NEW (created in workspace)                               │
│  ┌──────────────────┐                                            │
│  │ workspace/file   │──► ~/.gitmats/wsid/copies/file             │
│  └──────────────────┘                                            │
│  Disk: actual file size (no original)                            │
│                                                                   │
│  State: DELETED                                                   │
│  ┌──────────────────┐                                            │
│  │ workspace/file   │  (no symlink, file removed)               │
│  └──────────────────┘                                            │
│  Disk: 0 bytes                                                   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

## Git Integration

### Inherited Mode

When the original workspace has a Git repository:

```
┌─────────────────────────────────────────────────────────────────┐
│                   Inherited Git Mode                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Original:                                       │
│  ┌───────────────────────────────────────────────────────┐     │
│  │ .git/                                                  │     │
│  │ ├── objects/          (shared)                        │     │
│  │ ├── refs/             (shared)                        │     │
│  │ ├── worktrees/                                        │     │
│  │ │   └── gitmats-{id}/                                 │     │
│  │ │       ├── gitdir   -> ../workspaces/{id}/git        │     │
│  │ │       ├── HEAD     -> workspace branch              │     │
│  │ │       ├── index    -> workspace index               │     │
│  │ │       └── commondir -> ../../                       │     │
│  │ └── config            (shared)                        │     │
│  └───────────────────────────────────────────────────────┘     │
│                                                                  │
│  Workspace:                                 │
│  ┌───────────────────────────────────────────────────────┐     │
│  │ git/                                                  │     │
│  │ ├── HEAD              (independent)                   │     │
│  │ ├── index             (independent)                   │     │
│  │ ├── config.worktree   (per-worktree)                  │     │
│  │ ├── alternates        -> /original/.git/objects       │     │
│  │ └── refs/                                            │     │
│  │     └── gitmats/{id}/                                │     │
│  │         ├── base      (creation snapshot)            │     │
│  │         ├── cow-base  (last sync point)              │     │
│  │         └── head      (current state)                │     │
│  └───────────────────────────────────────────────────────┘     │
│                                                                  │
│  Benefits:                                                       │
│  - Zero object storage overhead (alternates)                    │
│  - Independent HEAD and index per workspace                     │
│  - Shared refs (can see original branches)                      │
│  - Git-native operations (status, log, commit work)             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Standalone Mode

When the original workspace has no Git repository:

```
┌─────────────────────────────────────────────────────────────────┐
│                   Standalone Git Mode                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Original: /data/reports (no .git)                              │
│  ┌───────────────────────────────────────────────────────┐     │
│  │ (no Git metadata)                                     │     │
│  │ reports/                                               │     │
│  │ ├── report1.pdf                                       │     │
│  │ ├── report2.pdf                                       │     │
│  │ └── summary.txt                                       │     │
│  └───────────────────────────────────────────────────────┘     │
│                                                                  │
│  Workspace:                                 │
│  ┌───────────────────────────────────────────────────────┐     │
│  │ git/                                                  │     │
│  │ ├── HEAD                                              │     │
│  │ ├── index                                             │     │
│  │ ├── objects/          (own object store)              │     │
│  │ │   └── pack/                                        │     │
│  │ └── refs/                                            │     │
│  │     └── heads/                                       │     │
│  │         └── main                                     │     │
│  └───────────────────────────────────────────────────────┘     │
│                                                                  │
│  Process:                                                        │
│  1. Initialize empty repo in workspace git/                     │
│  2. Create "virtual snapshot" commit from symlinks              │
│  3. Track COW modifications as normal commits                   │
│  4. Original directory never touched                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Versioning Backends

### Backend Interface

```python
class VersioningBackend(ABC):
    """
    Abstract interface for versioning backends.
    
    All backends must implement:
    - commit_changes: Create a versioned snapshot
    - get_history: Query version history
    - get_diff: Compare versions
    """
    
    @abstractmethod
    def commit_changes(self, workspace: Workspace, 
                       message: str) -> CommitResult:
        """Create a versioned snapshot of workspace state."""

    @abstractmethod
    def get_history(self, workspace: Workspace) -> List[CommitInfo]:
        """Get version history for workspace."""

    @abstractmethod
    def get_diff(self, workspace: Workspace,
                 from_version: str | None,
                 to_version: str | None) -> DiffResult:
        """Compare two versions or current state."""
```

### Local Git Backend

```python
class LocalGitBackend(VersioningBackend):
    """
    Default backend using local Git operations.
    
    Features:
    - Git-native commits and history
    - Shared objects via alternates (inherited mode)
    - Standard Git diff output
    - Works with existing Git workflows
    """
```

### LakeBase Backend

```python
class LakeBaseBackend(VersioningBackend):
    """
    Backend for database-native versioning via LakeBase API.
    
    Features:
    - Zero-copy database branching
    - LSN-based version tracking
    - Promote workflow (branch becomes main)
    - Schema + data versioning
    - Agent-friendly API
    """
```

### Null Backend

```python
class NullBackend(VersioningBackend):
    """
    Backend for ephemeral workspaces without version history.
    
    Features:
    - No commits (metadata only)
    - Minimal overhead
    - Suitable for throwaway experiments
    """
```

## Technology Stack

| Layer | Technology |
|-------|------------|
| Core Engine | Python 3.10+ |
| Git Integration | Git worktree + alternates |
| Versioning Backend | Local Git / LakeBase API / None |
| Storage | Symlinks + SQLite metadata |
| CLI | Click (Python CLI library) |