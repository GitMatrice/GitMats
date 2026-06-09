# GitMats

GitMats (Git Materialized Virtual Workspace) provides isolated virtual workspaces with zero disk overhead on creation. It uses symlink-based Copy-on-Write (COW) semantics to enable efficient parallel work on the same codebase without duplication.

## Features

- **Zero Disk Overhead**: Workspace creation uses symlinks, no file copying
- **Copy-on-Write**: Files are only copied when modified, saving disk space
- **Git Integration**: Full version control with worktree + alternates for object sharing
- **Isolation**: Each workspace is independent; modifications don't affect others
- **Pluggable Backends**: Local Git, LakeBase (database-native), or Null (ephemeral)
- **Safety**: Original workspace remains completely untouched

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/GitMats.git
cd GitMats

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install click httpx

# Install the package
pip install -e .
```

## Quick Start

```bash
# Create a virtual workspace from your project
gmt create my-feature --from=/path/to/project

# Navigate to the workspace
cd ~/.gitmats/workspaces/my-feature/workspace

# Make modifications - files are automatically COW'd on write
vim src/main.py

# Check workspace status
gmt status my-feature

# Commit changes
gmt commit my-feature -m "Add new feature"

# View history
gmt log my-feature

# When done, destroy the workspace
gmt destroy my-feature --force
```

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                          GitMats System                              │
├────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐│
│  │                         GMT CLI                                 ││
│  │   gmt create | list | status | commit | diff | destroy         ││
│  └────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│                              ▼                                       │
│  ┌────────────────────────────────────────────────────────────────┐│
│  │                    Workspace Manager                            ││
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────┐  ││
│  │  │ Workspace │ │ Git Engine│ │ COW Engine│ │ Metadata Mgr  │  ││
│  │  │ Factory   │ │           │ │           │ │               │  ││
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────────┘  ││
│  └────────────────────────────────────────────────────────────────┘│
│                              │                                       │
│            ┌─────────────────┴─────────────────┐                    │
│            ▼                                   ▼                    │
│  ┌──────────────────────┐       ┌──────────────────────────────────┐│
│  │   Original Workspace │       │   Virtual Workspace Storage      ││
│  │   (Read-Only Base)   │       │   ~/.gitmats/workspaces/         ││
│  │                      │◄──────│   ├── workspace/ (symlinks)      ││
│  │   /path/to/project   │       │   ├── copies/ (COW files)       ││
│  │                      │       │   ├── git/ (version control)     ││
│  └──────────────────────┘       │   └── metadata.db               ││
│                                 └──────────────────────────────────┘│
└────────────────────────────────────────────────────────────────────┘
```

## Workspace Types

| Type | Description | Git Integration |
|------|-------------|-----------------|
| **Inherited** | Original has Git repo | Shared objects via alternates, per-worktree HEAD |
| **Standalone** | Original has no Git | Independent git repo in workspace storage |
| **Database** | Original is a DB branch | LakeBase provides zero-copy branching |

## Versioning Backends

| Backend | Use Case | Description |
|---------|----------|-------------|
| **local** | Local development | Git worktree + alternates, Git-native operations |
| **lakebase** | Agent execution, CI/CD | Database-native versioning, promote workflow |
| **none** | Throwaway experiments | No version history, ephemeral workspaces |

## Directory Structure

```
~/.gitmats/
├── config.yaml                    # Global configuration
├── registry.db                    # Workspace registry
└── workspaces/
    └── my-feature/
        ├── workspace/             # Working directory (symlinks)
        ├── git/                   # Git metadata
        ├── copies/                # COW file copies
        ├── metadata.db            # File state tracking
        └── .gitmats.yaml          # Workspace config
```

## CLI Reference

See [docs/cli.md](docs/cli.md) for full command documentation.

### Essential Commands

```bash
# Workspace management
gmt create <id> [--from=<path>] [--backend=<type>]
gmt list [--verbose]
gmt status <id> [--files]
gmt destroy <id> [--force]

# Version control
gmt commit <id> -m "message"
gmt log <id>
gmt diff <id> [--vs-original]

# Configuration
gmt config set versioning.backend <type>
gmt config show
```

## Workflows

See [docs/workflows.md](docs/workflows.md) for detailed workflow examples:

- Basic workspace creation
- Agent speculative execution
- CI/CD preview environments
- Database migration sandbox
- Version restoration
- Backend migration

## Python API

```python
from gitmats import WorkspaceManager, GitMatsConfig, LocalGitBackend

# Configure GitMats
config = GitMatsConfig(
    gitmats_home=Path("~/.gitmats"),
    versioning_backend="local"
)

# Create workspace manager
manager = WorkspaceManager(config)

# Create a workspace
workspace = manager.create_workspace(
    workspace_id="my-feature",
    original_path="/path/to/project"
)

# Check status
status = manager.get_workspace_status("my-feature")
print(f"Files linked: {status.files_linked}")
print(f"Files copied: {status.files_copied}")

# Commit changes
backend = LocalGitBackend(config)
backend.commit_changes(workspace, message="Add feature")

# Destroy workspace
manager.destroy_workspace("my-feature", force=True)
```

## Documentation

- [CLI Reference](docs/cli.md) - Full command documentation
- [Workflows](docs/workflows.md) - Practical usage examples
- [Architecture](docs/architecture.md) - System design details

## Development

```bash
# Run tests
pytest tests/

# Run specific test module
pytest tests/test_workspace.py

# Run with coverage
pytest --cov=gitmats tests/
```

## License

Apache License 2.0 - see [LICENSE](LICENSE) file for details.