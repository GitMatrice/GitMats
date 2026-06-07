# GitMats Implementation Plan

## Overview

GitMats is a virtual workspace system that provides:
- Zero-disk overhead workspace creation (symlink-based)
- Copy-on-Write (COW) semantics for modifications
- Git integration for version control
- Pluggable versioning backends (Local Git, LakeBase, Null)

## Implementation Phases

### Phase 1: Core Foundation (Estimated: 3-4 days)

**Goal:** Basic data structures, configuration, and project scaffolding.

#### 1.1 Project Setup
- Create Python package structure (`gitmats/`)
- Setup dependencies (click/argparse for CLI, pytest for testing)
- Create base configuration schema (`config.yaml`)

#### 1.2 Core Data Models
- Implement `Workspace` dataclass (05-data-model.md)
- Implement `FileState` dataclass with status enum
- Implement `WorkspaceConfig` dataclass
- Implement `GitCommit` and `OperationLog` dataclasses

#### 1.3 Metadata Database
- Implement `MetadataManager` class
- Create global registry database schema (`~/.gitmats/registry.db`)
- Create per-workspace metadata database schema
- Implement CRUD operations for workspace registry
- Implement file state tracking methods

#### 1.4 Directory Structure Management
- Implement `~/.gitmats/` directory creation
- Implement workspace storage path resolution
- Implement workspace directory structure creation

**Tests for Phase 1:**
- Test data model serialization/deserialization
- Test database schema creation and migrations
- Test CRUD operations for registry
- Test directory structure creation

---

### Phase 2: COW Engine (Estimated: 4-5 days)

**Goal:** Implement copy-on-write file management.

#### 2.1 File Resolution
- Implement `COWEngine.resolve_path()` method
- Implement `FileSource` enum (ORIGINAL, COW_COPY, NEW, DELETED)
- Implement symlink state detection

#### 2.2 Symlink Management
- Implement symlink creation for files
- Implement directory structure creation (actual directories, not symlinks)
- Implement symlink validation and integrity checks

#### 2.3 Copy-Up Operations
- Implement `COWEngine.copy_up()` method
- Implement COW directory creation
- Implement file copying with hash computation
- Implement symlink update after copy
- Implement metadata recording

#### 2.4 File Creation/Deletion
- Implement `COWEngine.create_new_file()` method
- Implement `COWEngine.delete_file()` method
- Implement metadata state transitions

#### 2.5 Hash Computation
- Implement SHA-256 hash computation for files
- Implement hash comparison for change detection

**Tests for Phase 2:**
- Test symlink creation and resolution
- Test copy-up operation (single file, nested paths)
- Test file creation in workspace
- Test file deletion from workspace
- Test hash computation accuracy
- Test symlink validation

---

### Phase 3: Local Git Backend (Estimated: 5-6 days)

**Goal:** Implement Git integration for versioned workspaces.

#### 3.1 Git Engine Core
- Implement `GitEngine` class
- Implement workspace type detection (`detect_workspace_type()`)

#### 3.2 Inherited Mode (Original has Git)
- Implement `setup_inherited_git()` method
- Implement worktree administrative directory creation
- Implement gitdir/commondir/HEAD files
- Implement alternates file for object sharing
- Implement workspace branch creation
- Implement GitMats refs (`refs/gitmats/{id}/base`, `last-sync`)

#### 3.3 Standalone Mode (Original has no Git)
- Implement `setup_standalone_git()` method
- Implement independent Git repository initialization
- Implement virtual base commit creation
- Implement git index file writing
- Implement tree object creation from index

#### 3.4 Git Operations
- Implement `git_status()` for workspace
- Implement `git_add()` for staging COW files
- Implement `git_commit()` with message
- Implement `git_log()` for history viewing
- Implement `git_diff()` for change comparison

#### 3.5 Git Hooks Integration
- Implement `GitHooksManager` class
- Implement pre-commit hook (COW sync)
- Implement post-commit hook (metadata update)
- Implement hook installation in workspace

**Tests for Phase 3:**
- Test inherited Git setup (with existing Git repo)
- Test standalone Git setup (without existing Git)
- Test worktree structure creation
- Test alternates file functionality
- Test git status/add/commit operations
- Test git log/diff operations
- Test hook installation and execution

---

### Phase 4: Workspace Manager (Estimated: 3-4 days)

**Goal:** Orchestration layer for workspace lifecycle.

#### 4.1 Workspace Factory
- Implement `WorkspaceManager.create_workspace()` method
- Implement workspace ID validation
- Implement original path resolution
- Implement workspace type auto-detection
- Implement COW engine initialization
- Implement Git engine initialization

#### 4.2 Workspace Lifecycle
- Implement `WorkspaceManager.destroy_workspace()` method
- Implement cleanup of COW copies
- Implement cleanup of Git worktree
- Implement metadata cleanup
- Implement workspace locking/unlocking

#### 4.3 Workspace Statistics
- Implement disk usage calculation
- Implement file count statistics
- Implement savings ratio computation

**Tests for Phase 4:**
- Test workspace creation (inherited and standalone)
- Test workspace destruction
- Test workspace locking
- Test statistics calculation
- Test error handling (invalid paths, duplicate IDs)

---

### Phase 5: CLI Implementation (Estimated: 4-5 days)

**Goal:** Implement `gmt` CLI tool.

#### 5.1 CLI Framework
- Implement `GMTCLI` command dispatcher
- Implement argument parsing with click/argparse
- Implement help and usage output

#### 5.2 Workspace Commands
- Implement `gmt create` command
- Implement `gmt list` command
- Implement `gmt status` command
- Implement `gmt destroy` command
- Implement `gmt prune` command

#### 5.3 Version Control Commands
- Implement `gmt commit` command
- Implement `gmt diff` command
- Implement `gmt log` command
- Implement `gmt branch` command
- Implement `gmt sync` command

#### 5.4 File Commands
- Implement `gmt files` command
- Implement `gmt reset` command
- Implement `gmt export` command

#### 5.5 Internal Commands
- Implement `gmt internal sync-cow` command
- Implement `gmt internal update-metadata` command
- Implement `gmt internal validate` command

#### 5.6 Configuration Commands
- Implement `gmt config set` command
- Implement `gmt config show` command

**Tests for Phase 5:**
- Test each command with various arguments
- Test output formatting
- Test error handling and messages
- Test integration with WorkspaceManager

---

### Phase 6: Null Backend (Estimated: 1-2 days)

**Goal:** Implement no-versioning backend for ephemeral workspaces.

#### 6.1 NullBackend Implementation
- Implement `NullBackend` class (VersioningBackend interface)
- Implement metadata-only tracking
- Implement skip-commit behavior
- Implement workspace destruction without branch cleanup

**Tests for Phase 6:**
- Test workspace creation with null backend
- Test COW operations without Git
- Test file state tracking

---

### Phase 7: LakeBase Backend (Estimated: 5-6 days)

**Goal:** Implement pluggable LakeBase versioning backend.

#### 7.1 Backend Interface
- Implement `VersioningBackend` abstract base class
- Define interface methods (create_branch, commit, list_versions, etc.)

#### 7.2 LakeBase Client
- Implement `LakeBaseClient` for API communication
- Implement authentication with API token
- Implement error handling for API responses

#### 7.3 LakeBase Backend Implementation
- Implement `LakeBaseBackend.create_workspace_branch()`
- Implement `LakeBaseBackend.commit()` (version creation)
- Implement `LakeBaseBackend.list_versions()`
- Implement `LakeBaseBackend.get_version()`
- Implement `LakeBaseBackend.diff_versions()`
- Implement `LakeBaseBackend.restore_version()`
- Implement `LakeBaseBackend.delete_branch()`

#### 7.4 File Metadata Sync
- Implement `_sync_file_metadata()` for file-based workspaces
- Implement `_rebuild_cow_from_version()` for restoration
- Implement `_ensure_compute()` for compute management

#### 7.5 Configuration
- Implement LakeBase configuration validation
- Implement backend selection logic
- Implement workspace-specific backend override

**Tests for Phase 7:**
- Test backend interface compliance
- Test LakeBase API client (mocked or test server)
- Test branch creation/deletion
- Test version creation and listing
- Test diff and restore operations
- Test configuration handling

---

### Phase 8: Integration and Polish (Estimated: 2-3 days)

**Goal:** Final integration, documentation, and polish.

#### 8.1 End-to-End Integration
- Test complete workflows from CLI
- Test backend switching
- Test workspace migration

#### 8.2 Error Handling
- Implement comprehensive error handling
- Implement user-friendly error messages
- Implement graceful degradation

#### 8.3 Documentation
- Write CLI usage documentation
- Write configuration guide
- Write backend setup guides

#### 8.4 Performance Optimization
- Optimize hash computation for large files
- Optimize symlink creation for large directories
- Implement lazy metadata updates

---

## Implementation Order (Detailed)

### Week 1: Foundation

| Day | Task | Files to Create |
|-----|------|-----------------|
| 1 | Project setup, data models | `gitmats/__init__.py`, `gitmats/models.py` |
| 2 | Metadata database | `gitmats/metadata.py` |
| 3 | Directory structure | `gitmats/storage.py` |
| 4 | Tests for Phase 1 | `tests/test_models.py`, `tests/test_metadata.py` |

### Week 2: COW Engine

| Day | Task | Files to Create |
|-----|------|-----------------|
| 5 | Symlink management | `gitmats/cow/symlinks.py` |
| 6 | Copy-up operations | `gitmats/cow/engine.py` |
| 7 | File creation/deletion | `gitmats/cow/engine.py` (extend) |
| 8 | Hash computation | `gitmats/cow/hash.py` |
| 9-10 | Tests for Phase 2 | `tests/test_cow.py` |

### Week 3: Git Integration

| Day | Task | Files to Create |
|-----|------|-----------------|
| 11 | Git engine core | `gitmats/git/engine.py` |
| 12 | Inherited mode setup | `gitmats/git/inherited.py` |
| 13 | Standalone mode setup | `gitmats/git/standalone.py` |
| 14 | Git operations | `gitmats/git/operations.py` |
| 15 | Git hooks | `gitmats/git/hooks.py` |
| 16-17 | Tests for Phase 3 | `tests/test_git.py` |

### Week 4: Workspace Manager & CLI

| Day | Task | Files to Create |
|-----|------|-----------------|
| 18 | Workspace manager | `gitmats/manager.py` |
| 19 | Workspace lifecycle | `gitmats/manager.py` (extend) |
| 20 | CLI framework | `gitmats/cli/__init__.py` |
| 21 | Workspace commands | `gitmats/cli/workspace.py` |
| 22 | VC commands | `gitmats/cli/versioning.py` |
| 23-24 | Tests | `tests/test_manager.py`, `tests/test_cli.py` |

### Week 5: Backends

| Day | Task | Files to Create |
|-----|------|-----------------|
| 25 | Backend interface | `gitmats/backends/base.py` |
| 26 | Null backend | `gitmats/backends/null.py` |
| 27-28 | LakeBase client | `gitmats/backends/lakebase_client.py` |
| 29-30 | LakeBase backend | `gitmats/backends/lakebase.py` |

### Week 6: Integration

| Day | Task | Files to Create |
|-----|------|-----------------|
| 31-32 | End-to-end tests | `tests/test_e2e.py` |
| 33 | Error handling polish | All files (review) |
| 34 | Documentation | `docs/` |
| 35 | Performance optimization | All files (optimize) |

---

## File Structure

```
gitmats/
├── __init__.py           # Package entry, version
├── config.py             # Configuration loading and validation
├── models.py             # Data models (Workspace, FileState, etc.)
├── storage.py            # Directory structure management
├── metadata.py           # MetadataManager (SQLite operations)
├── manager.py            # WorkspaceManager (orchestration)
├── cow/
│   ├── __init__.py
│   ├── engine.py         # COWEngine (copy-up, file ops)
│   ├── symlinks.py       # Symlink management
│   └── hash.py           # Hash computation utilities
├── git/
│   ├── __init__.py
│   ├── engine.py         # GitEngine (core Git operations)
│   ├── inherited.py      # Inherited mode setup
│   ├── standalone.py     # Standalone mode setup
│   ├── operations.py     # Git status/commit/diff
│   └── hooks.py          # Git hooks integration
├── backends/
│   ├── __init__.py
│   ├── base.py           # VersioningBackend ABC
│   ├── local.py          # LocalGitBackend (wraps GitEngine)
│   ├── null.py           # NullBackend
│   ├── lakebase.py       # LakeBaseBackend
│   └── lakebase_client.py # LakeBase API client
├── cli/
│   ├── __init__.py       # CLI entry point
│   ├── workspace.py      # create, list, status, destroy
│   ├── versioning.py     # commit, diff, log, sync
│   ├── files.py          # files, reset, export
│   ├── config.py         # config set, show
│   └── internal.py       # sync-cow, validate
└── utils/
    ├── __init__.py
    ├── paths.py          # Path resolution utilities
    ├── hash.py           # Shared hash utilities
    └── display.py        # Output formatting

tests/
├── __init__.py
├── conftest.py           # Test fixtures
├── test_models.py        # Data model tests
├── test_metadata.py      # Metadata tests
├── test_cow.py           # COW engine tests
├── test_git.py           # Git integration tests
├── test_manager.py       # Workspace manager tests
├── test_cli.py           # CLI tests
├── test_backends.py      # Backend tests
├── test_e2e.py           # End-to-end workflow tests
└── fixtures/             # Test fixtures (sample repos)
    ├── sample_repo/      # Sample Git repository
    └── sample_non_git/   # Sample non-Git directory
```

---

## Dependencies

```toml
# pyproject.toml
[project]
name = "gitmats"
version = "0.1.0"
requires-python = ">=3.10"

dependencies = [
    "click>=8.0",          # CLI framework
    "pyyaml>=6.0",         # Configuration
    "rich>=13.0",          # Terminal output
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "black>=23.0",
    "ruff>=0.1.0",
    "mypy>=1.0",
]
```

---

## Key Design Decisions

1. **Python 3.10+**: Use modern Python features (dataclasses, type hints, pattern matching)
2. **Click for CLI**: Git-style command structure, easy subcommand implementation
3. **SQLite for metadata**: Fast queries, embedded, no external dependencies
4. **Symlink-based COW**: Zero disk overhead, simple implementation
5. **Git worktree for inherited mode**: Native Git integration, independent HEAD/index
6. **Pluggable backends**: Interface-based, allows future extensions

---

## Testing Strategy

1. **Unit tests**: Each module has isolated unit tests
2. **Integration tests**: Test module interactions (COW + Git, Manager + Backend)
3. **E2E tests**: Complete workflow tests (CLI → Manager → Backend)
4. **Fixture-based**: Use sample Git repo and non-Git directory for testing
5. **Mock LakeBase API**: Use responses library for LakeBase backend tests

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Git worktree complexity | Extensive testing with real Git operations |
| Symlink edge cases (broken, circular) | Validation checks, error handling |
| LakeBase API changes | Client abstraction, versioned API endpoints |
| Large file performance | Chunked hash computation, lazy loading |
| Cross-platform compatibility | Platform-specific tests, path normalization |

---

## Success Criteria

1. **Functional**: All CLI commands work as specified in design
2. **Performance**: Workspace creation < 1s for 1000 files
3. **Reliability**: No data loss, original workspace never modified
4. **Test coverage**: > 90% for core modules
5. **Documentation**: Complete CLI usage guide and backend setup