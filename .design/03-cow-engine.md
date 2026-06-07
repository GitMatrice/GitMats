# Copy-on-Write Engine Design

## Overview

The COW (Copy-on-Write) engine is the core mechanism that enables GitMats to provide isolated virtual workspaces with minimal disk overhead. It implements lazy copying - files are only duplicated when modifications occur.

## COW Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                         COW Engine Flow                                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐         │
│  │  Read Path   │      │  Write Path  │      │  Delete Path │         │
│  │              │      │              │      │              │         │
│  │  1. Check    │      │  1. Check    │      │  1. Mark     │         │
│  │     metadata │      │     metadata │      │     deleted  │         │
│  │  2. Resolve  │      │  2. If linked│      │  2. Update   │         │
│  │     symlink  │      │     copy_up  │      │     symlink  │         │
│  │  3. Return   │      │  3. Update   │      │  3. Update   │         │
│  │     content  │      │     symlink  │      │     metadata │         │
│  │              │      │  4. Write    │      │  4. Notify   │         │
│  │  O(1) path   │      │     content  │      │     Git      │         │
│  │  lookup      │      │              │      │              │         │
│  └──────────────┘      │  O(n) copy   │      │  O(1) mark   │         │
│                        │  (n=file size)│      │              │         │
│                        └──────────────┘      └──────────────┘         │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
```

## Core Operations

### 1. File Resolution

```python
class COWEngine:
    """
    Copy-on-Write engine implementation.
    """
    
    def resolve_path(self, workspace: Workspace, rel_path: str) -> ResolvedPath:
        """
        Resolve actual path for a file in virtual workspace.
        
        Returns ResolvedPath with:
        - actual_path: Where to read/write
        - source: ORIGINAL, COW_COPY, NEW, or DELETED
        - symlink_target: What the symlink points to
        """
        
        # Check metadata first
        state = self.metadata.get_file_state(workspace.id, rel_path)
        
        if state.status == 'deleted':
            raise FileNotFoundError(f"File deleted in workspace: {rel_path}")
        
        if state.status in ['copied', 'new']:
            # File has been modified/created - use COW copy
            return ResolvedPath(
                actual_path=workspace.copies / rel_path,
                source=FileSource.COW_COPY if state.status == 'copied' else FileSource.NEW,
                symlink_target=workspace.copies / rel_path
            )
        
        # File is linked to original - use original
        original_path = workspace.original / rel_path
        if not original_path.exists():
            raise FileNotFoundError(f"File not found: {rel_path}")
        
        return ResolvedPath(
            actual_path=original_path,
            source=FileSource.ORIGINAL,
            symlink_target=original_path
        )
```

### 2. Copy-Up (COW Trigger)

```python
def copy_up(self, workspace: Workspace, rel_path: str,
            content: bytes | None = None) -> CopyUpResult:
    """
    Execute copy-on-write operation.
    
    This is triggered when:
    - User opens file for write
    - VFS detects write intent
    - Git needs to stage modified file
    
    Process:
    1. Check if already copied (skip if yes)
    2. Create COW directory structure
    3. Copy file from original to COW storage
    4. Remove existing symlink in workspace
    5. Create new symlink to COW copy
    6. Update metadata
    7. Optionally write new content
    8. Notify Git engine
    
    Args:
        workspace: Target workspace
        rel_path: Relative path of file
        content: Optional new content to write after copy
    
    Returns:
        CopyUpResult with paths and metadata
    """
    
    # 1. Check if already copied
    state = self.metadata.get_file_state(workspace.id, rel_path)
    if state.status in ['copied', 'new']:
        # Already in COW layer - just update if content provided
        if content is not None:
            cow_path = workspace.copies / rel_path
            cow_path.write_bytes(content)
            self.metadata.update_cow_hash(workspace.id, rel_path, 
                                          compute_hash(content))
        return CopyUpResult(skipped=True, path=workspace.copies / rel_path)
    
    # 2. Check if file exists in original
    original_path = workspace.original / rel_path
    if not original_path.exists():
        # New file (doesn't exist in original)
        return self.create_new_file(workspace, rel_path, content or b'')
    
    # 3. Create COW directory
    cow_path = workspace.copies / rel_path
    cow_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 4. Copy file
    original_hash = compute_hash(original_path)
    shutil.copy2(original_path, cow_path)
    
    # 5. Write content if provided
    if content is not None:
        cow_path.write_bytes(content)
    
    cow_hash = compute_hash(cow_path)
    
    # 6. Update symlink in workspace
    workspace_path = workspace.workspace_dir / rel_path
    if workspace_path.exists() or workspace_path.is_symlink():
        workspace_path.unlink()
    workspace_path.symlink_to(cow_path)
    
    # 7. Update metadata
    self.metadata.record_copy_up(
        workspace_id=workspace.id,
        rel_path=rel_path,
        original_hash=original_hash,
        original_size=original_path.stat().st_size,
        cow_path=str(cow_path),
        cow_hash=cow_hash,
        cow_size=cow_path.stat().st_size
    )
    
    # 8. Notify Git
    self.git_engine.on_file_modified(workspace, rel_path)
    
    return CopyUpResult(
        skipped=False,
        original_path=original_path,
        cow_path=cow_path,
        original_hash=original_hash,
        cow_hash=cow_hash
    )
```

### 3. Create New File

```python
def create_new_file(self, workspace: Workspace, 
                    rel_path: str, 
                    content: bytes) -> NewFileResult:
    """
    Create a new file that doesn't exist in original.
    
    Process:
    1. Create COW directory
    2. Write content to COW storage
    3. Create symlink in workspace
    4. Update metadata as 'new'
    5. Notify Git
    """
    
    cow_path = workspace.copies / rel_path
    workspace_path = workspace.workspace_dir / rel_path
    
    # Create directory structure
    cow_path.parent.mkdir(parents=True, exist_ok=True)
    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write content
    cow_path.write_bytes(content)
    
    # Create symlink
    workspace_path.symlink_to(cow_path)
    
    # Update metadata
    self.metadata.record_new_file(
        workspace_id=workspace.id,
        rel_path=rel_path,
        cow_path=str(cow_path),
        cow_hash=compute_hash(content),
        cow_size=len(content)
    )
    
    # Notify Git
    self.git_engine.on_file_created(workspace, rel_path)
    
    return NewFileResult(path=cow_path, hash=compute_hash(content))
```

### 4. Delete File

```python
def delete_file(self, workspace: Workspace, rel_path: str) -> DeleteResult:
    """
    Delete a file from virtual workspace.
    
    Note: Original file is never deleted.
    
    Process:
    1. Check file state
    2. Remove symlink (workspace)
    3. Remove COW copy if exists
    4. Mark as 'deleted' in metadata
    5. Notify Git
    """
    
    state = self.metadata.get_file_state(workspace.id, rel_path)
    workspace_path = workspace.workspace_dir / rel_path
    
    # Remove symlink
    if workspace_path.exists() or workspace_path.is_symlink():
        workspace_path.unlink()
    
    # Remove COW copy if exists
    if state.status in ['copied', 'new']:
        cow_path = workspace.copies / rel_path
        if cow_path.exists():
            cow_path.unlink()
    
    # Update metadata
    self.metadata.record_deletion(workspace.id, rel_path)
    
    # Notify Git
    self.git_engine.on_file_deleted(workspace, rel_path)
    
    return DeleteResult(success=True)
```

## Directory Handling

### Directory Symlink Strategy

Directories are handled differently from files:

```python
def create_workspace_structure(self, workspace: Workspace) -> None:
    """
    Create initial workspace directory structure.
    
    Strategy:
    - Directories: Create actual directories (not symlinks)
    - Files: Create symlinks to original
    
    Rationale:
    - Directories need to be writable (can add new files)
    - Files can be symlinked until modified
    """
    
    original = Path(workspace.original)
    workspace_wd = Path(workspace.workspace_dir)
    
    for item in original.rglob('*'):
        rel_path = item.relative_to(original)
        virtual_path = workspace_wd / rel_path
        
        if item.is_dir():
            # Create actual directory (allows adding files)
            virtual_path.mkdir(parents=True, exist_ok=True)
            
        elif item.is_file():
            # Create symlink to original file
            virtual_path.parent.mkdir(parents=True, exist_ok=True)
            virtual_path.symlink_to(item)
            
            # Record in metadata as 'linked'
            self.metadata.record_linked_file(
                workspace_id=workspace.id,
                rel_path=str(rel_path),
                original_hash=compute_hash(item),
                original_size=item.stat().st_size
            )
```

### Nested Directory COW

When a file in nested directory is modified:

```python
def ensure_cow_directory(self, workspace: Workspace, rel_path: str) -> Path:
    """
    Ensure COW directory exists for file path.
    
    Creates intermediate directories in COW storage
    without touching original directory structure.
    """
    
    cow_path = workspace.copies / rel_path
    cow_dir = cow_path.parent
    
    # Create all parent directories in COW storage
    cow_dir.mkdir(parents=True, exist_ok=True)
    
    return cow_path
```

## Symlink Management

### Symlink Types

```
┌─────────────────────────────────────────────────────────────────┐
│                    Symlink States                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  State: LINKED (initial)                                         │
│  ┌──────────────────┐                                           │
│  │ workspace/file   │──► /original/file                         │
│  └──────────────────┘                                           │
│  Disk: 0 bytes (symlink only)                                   │
│                                                                  │
│  State: COPIED (after modification)                             │
│  ┌──────────────────┐                                           │
│  │ workspace/file   │──► ~/.gitmats/wsid/copies/file            │
│  └──────────────────┘                                           │
│  Disk: actual file size in copies/                              │
│                                                                  │
│  State: NEW (created in workspace)                              │
│  ┌──────────────────┐                                           │
│  │ workspace/file   │──► ~/.gitmats/wsid/copies/file            │
│  └──────────────────┘                                           │
│  Disk: actual file size (no original)                           │
│                                                                  │
│  State: DELETED                                                  │
│  ┌──────────────────┐                                           │
│  │ workspace/file   │  (no symlink, file removed)              │
│  └──────────────────┘                                           │
│  Disk: 0 bytes                                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Symlink Validation

```python
def validate_symlink(self, workspace: Workspace, 
                     rel_path: str) -> SymlinkStatus:
    """
    Validate symlink integrity.
    
    Checks:
    1. Symlink exists in workspace
    2. Target exists
    3. Target matches metadata state
    4. Content hash matches metadata
    """
    
    workspace_path = workspace.workspace_dir / rel_path
    state = self.metadata.get_file_state(workspace.id, rel_path)
    
    if not workspace_path.is_symlink():
        if state.status == 'deleted':
            return SymlinkStatus.VALID_DELETED
        return SymlinkStatus.INVALID_NO_SYMLINK
    
    target = workspace_path.resolve()
    
    if state.status == 'linked':
        expected_target = workspace.original / rel_path
        if target != expected_target:
            return SymlinkStatus.INVALID_TARGET
    
    elif state.status in ['copied', 'new']:
        expected_target = workspace.copies / rel_path
        if target != expected_target:
            return SymlinkStatus.INVALID_TARGET
    
    if not target.exists():
        return SymlinkStatus.INVALID_TARGET_MISSING
    
    # Verify content hash
    current_hash = compute_hash(target)
    if state.status == 'linked':
        if current_hash != state.original_hash:
            return SymlinkStatus.INVALID_HASH
    else:
        if current_hash != state.cow_hash:
            return SymlinkStatus.INVALID_HASH
    
    return SymlinkStatus.VALID
```

## Metadata Integration

### File State Tracking

```python
class COWMetadata:
    """
    Metadata tracking for COW operations.
    
    Schema:
    ┌──────────────────────────────────────────────────────────┐
    │ file_state                                                │
    ├──────────────────────────────────────────────────────────┤
    │ relative_path     │ TEXT PRIMARY KEY                     │
    │ state             │ TEXT ('linked', 'copied', 'new', 'deleted') │
    │ original_hash     │ TEXT (SHA-256)                        │
    │ original_size     │ INTEGER                               │
    │ cow_path          │ TEXT                                  │
    │ cow_hash          │ TEXT (SHA-256)                        │
    │ cow_size          │ INTEGER                               │
    │ first_modified    │ REAL (timestamp)                      │
    │ last_modified     │ REAL (timestamp)                      │
    │ modification_count│ INTEGER                               │
    └──────────────────────────────────────────────────────────┘
    """
    
    def record_linked_file(self, workspace_id: str, rel_path: str,
                           original_hash: str, original_size: int) -> None:
        """Record initial symlink state."""
        
        conn = sqlite3.connect(self.db_path(workspace_id))
        conn.execute("""
            INSERT INTO file_state 
            (relative_path, state, original_hash, original_size)
            VALUES (?, 'linked', ?, ?)
        """, (rel_path, original_hash, original_size))
        conn.commit()
        conn.close()
    
    def record_copy_up(self, workspace_id: str, rel_path: str,
                       original_hash: str, original_size: int,
                       cow_path: str, cow_hash: str, cow_size: int) -> None:
        """Record COW operation."""
        
        conn = sqlite3.connect(self.db_path(workspace_id))
        now = time.time()
        conn.execute("""
            INSERT OR REPLACE INTO file_state 
            (relative_path, state, original_hash, original_size,
             cow_path, cow_hash, cow_size, first_modified, 
             last_modified, modification_count)
            VALUES (?, 'copied', ?, ?, ?, ?, ?, ?, ?, 1)
        """, (rel_path, original_hash, original_size, 
              cow_path, cow_hash, cow_size, now, now))
        conn.commit()
        conn.close()
    
    def update_cow_hash(self, workspace_id: str, rel_path: str,
                        new_hash: str) -> None:
        """Update hash after content modification."""
        
        conn = sqlite3.connect(self.db_path(workspace_id))
        conn.execute("""
            UPDATE file_state
            SET cow_hash = ?, 
                last_modified = ?,
                modification_count = modification_count + 1
            WHERE relative_path = ?
        """, (new_hash, time.time(), rel_path))
        conn.commit()
        conn.close()
    
    def get_file_state(self, workspace_id: str, 
                       rel_path: str) -> FileState:
        """Query file state."""
        
        conn = sqlite3.connect(self.db_path(workspace_id))
        cursor = conn.execute("""
            SELECT * FROM file_state WHERE relative_path = ?
        """, (rel_path,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return FileState(status='unknown')
        
        return FileState(
            rel_path=row[0],
            status=row[1],
            original_hash=row[2],
            original_size=row[3],
            cow_path=row[4],
            cow_hash=row[5],
            cow_size=row[6],
            first_modified=row[7],
            last_modified=row[8],
            modification_count=row[9]
        )
```

## Performance Optimizations

### Batch Copy-Up

```python
def batch_copy_up(self, workspace: Workspace, 
                   paths: list[str]) -> BatchResult:
    """
    Batch copy-up for multiple files.
    
    More efficient than individual copy-ups:
    - Single metadata transaction
    - Parallel file copying
    - Single Git notification
    """
    
    results = []
    
    # Filter already-copied files
    to_copy = []
    for path in paths:
        state = self.metadata.get_file_state(workspace.id, path)
        if state.status == 'linked':
            to_copy.append(path)
    
    # Parallel copy
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(self.copy_up_file_only, workspace, p): p
            for p in to_copy
        }
        
        for future in as_completed(futures):
            path = futures[future]
            result = future.result()
            results.append(result)
    
    # Batch metadata update
    self.metadata.batch_update(workspace.id, results)
    
    # Single Git notification
    self.git_engine.on_batch_modified(workspace, to_copy)
    
    return BatchResult(results=results, count=len(results))
```

### Hash Caching

```python
class HashCache:
    """
    Cache file hashes to avoid recomputation.
    
    Uses in-memory cache with LRU eviction.
    """
    
    def __init__(self, max_size: int = 10000):
        self.cache = OrderedDict()
        self.max_size = max_size
    
    def get_hash(self, path: Path) -> str:
        """Get cached hash or compute."""
        
        # Check cache
        cache_key = str(path)
        if cache_key in self.cache:
            self.cache.move_to_end(cache_key)  # LRU update
            return self.cache[cache_key]
        
        # Compute hash
        hash_value = compute_hash(path)
        
        # Store in cache
        self.cache[cache_key] = hash_value
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)  # Evict oldest
        
        return hash_value
    
    def invalidate(self, path: Path) -> None:
        """Remove from cache when file changes."""
        
        cache_key = str(path)
        if cache_key in self.cache:
            del self.cache[cache_key]
```

## COW Statistics

```python
def get_cow_stats(self, workspace: Workspace) -> COWStatistics:
    """
    Calculate COW statistics for workspace.
    
    Returns:
    - total_files: All files tracked
    - linked_files: Still symlinked to original
    - copied_files: COW copies created
    - new_files: Created in workspace
    - deleted_files: Marked deleted
    - disk_usage: Bytes used by COW copies
    - savings_ratio: Disk saved vs full copy
    """
    
    conn = sqlite3.connect(self.metadata.db_path(workspace.id))
    
    cursor = conn.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN state='linked' THEN 1 ELSE 0 END) as linked,
            SUM(CASE WHEN state='copied' THEN 1 ELSE 0 END) as copied,
            SUM(CASE WHEN state='new' THEN 1 ELSE 0 END) as new,
            SUM(CASE WHEN state='deleted' THEN 1 ELSE 0 END) as deleted,
            SUM(COALESCE(cow_size, 0)) as disk_usage,
            SUM(COALESCE(original_size, 0)) as original_total
        FROM file_state
    """)
    
    row = cursor.fetchone()
    conn.close()
    
    total_files = row[0]
    linked_files = row[1]
    copied_files = row[2]
    new_files = row[3]
    deleted_files = row[4]
    disk_usage = row[5]
    original_total = row[6]
    
    # Calculate savings ratio
    # Full copy would use original_total bytes
    # COW only uses disk_usage bytes
    savings_ratio = 1.0 - (disk_usage / original_total) if original_total > 0 else 0
    
    return COWStatistics(
        total_files=total_files,
        linked_files=linked_files,
        copied_files=copied_files,
        new_files=new_files,
        deleted_files=deleted_files,
        disk_usage_bytes=disk_usage,
        savings_ratio=savings_ratio,
        savings_percent=savings_ratio * 100
    )
```

## COW + Git Integration

```python
class COWGitBridge:
    """
    Bridge between COW engine and Git.
    
    Ensures Git is aware of COW operations.
    """
    
    def on_file_modified(self, workspace: Workspace, 
                         rel_path: str) -> None:
        """
        Called by COW engine after copy_up.
        
        Git actions:
        1. Add new blob to object store
        2. Update index entry
        3. File now shows as 'modified' in git status
        """
        
        cow_path = workspace.copies / rel_path
        
        # Add blob to git
        blob_sha = self.git.add_blob(workspace.git, cow_path)
        
        # Update index
        mode = get_git_mode(cow_path)
        self.git.update_index(
            workspace.git,
            mode=mode,
            sha=blob_sha,
            path=rel_path
        )
    
    def on_file_created(self, workspace: Workspace,
                        rel_path: str) -> None:
        """
        Called when new file created in workspace.
        
        Git actions:
        1. Add blob
        2. Add to index as new entry
        """
        
        cow_path = workspace.copies / rel_path
        
        blob_sha = self.git.add_blob(workspace.git, cow_path)
        mode = get_git_mode(cow_path)
        
        self.git.add_to_index(
            workspace.git,
            mode=mode,
            sha=blob_sha,
            path=rel_path,
            stage=0  # Normal stage
        )
    
    def on_file_deleted(self, workspace: Workspace,
                        rel_path: str) -> None:
        """
        Called when file deleted in workspace.
        
        Git actions:
        1. Remove from index
        2. File shows as 'deleted' in git status
        """
        
        self.git.remove_from_index(workspace.git, rel_path)
    
    def sync_to_git_commit(self, workspace: Workspace,
                           message: str) -> str:
        """
        Commit all COW changes to Git.
        
        Creates git commit representing current COW state.
        """
        
        # Write tree from index
        tree_sha = self.git.write_tree(workspace.git)
        
        # Get parent
        parent_sha = self.git.get_head(workspace.git)
        
        # Create commit
        commit_sha = self.git.create_commit(
            workspace.git,
            tree=tree_sha,
            parent=parent_sha,
            message=message
        )
        
        # Update HEAD
        self.git.update_head(workspace.git, commit_sha)
        
        return commit_sha
```

## Error Handling

```python
class COWError(Exception):
    """Base exception for COW operations."""

class CopyUpError(COWError):
    """Failed to copy file."""
    def __init__(self, rel_path: str, reason: str):
        self.rel_path = rel_path
        self.reason = reason
        super().__init__(f"Copy-up failed for {rel_path}: {reason}")

class SymlinkError(COWError):
    """Symlink operation failed."""
    def __init__(self, rel_path: str, operation: str, reason: str):
        self.rel_path = rel_path
        self.operation = operation
        self.reason = reason
        super().__init__(f"Symlink {operation} failed for {rel_path}: {reason}")

class MetadataError(COWError):
    """Metadata operation failed."""
    def __init__(self, rel_path: str, operation: str):
        self.rel_path = rel_path
        self.operation = operation
        super().__init__(f"Metadata {operation} failed for {rel_path}")

def safe_copy_up(self, workspace: Workspace, rel_path: str) -> CopyUpResult:
    """
    Safe copy-up with error handling.
    
    Handles:
    - File not found
    - Permission denied
    - Disk full
    - Symlink creation failure
    """
    
    try:
        return self.copy_up(workspace, rel_path)
    
    except FileNotFoundError:
        # Original file doesn't exist - create new
        return self.create_new_file(workspace, rel_path, b'')
    
    except PermissionError as e:
        raise CopyUpError(rel_path, f"Permission denied: {e}")
    
    except OSError as e:
        if e.errno == errno.ENOSPC:
            raise CopyUpError(rel_path, "Disk full")
        raise CopyUpError(rel_path, f"OS error: {e}")
    
    except Exception as e:
        raise CopyUpError(rel_path, f"Unexpected error: {e}")
```