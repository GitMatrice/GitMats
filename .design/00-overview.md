# GitMats Design Overview

## Project Goal

GitMats (Git Materialized Virtual Workspace) provides isolated virtual workspaces with:
- Zero disk overhead on creation (symlink-based)
- Copy-on-write semantics for modifications
- Full Git integration for version control
- Read-only original workspace protection

## Design Documents

| Document | Description |
|----------|-------------|
| [01-architecture.md](./01-architecture.md) | System architecture and components |
| [02-git-integration.md](./02-git-integration.md) | Git integration strategies (versioned/non-versioned) |
| [03-cow-engine.md](./03-cow-engine.md) | Copy-on-write implementation details |
| [04-gmt-cli.md](./04-gmt-cli.md) | gmt CLI design (Git-style commands) |
| [05-data-model.md](./05-data-model.md) | Metadata and state management |
| [06-lakebase-plugin-design.md](./06-lakebase-plugin-design.md) | Pluggable LakeBase versioning backend |
| [07-workflows.md](./07-workflows.md) | User workflows and examples |

## Core Concepts

### Versioning Backend Types

GitMats supports pluggable versioning backends for storing commits:

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitMats Versioning Backends                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────┐       ┌────────────────────────────┐   │
│  │ LocalGitBackend    │       │ LakeBaseBackend            │   │
│  │ (default)          │       │ (pluggable)                │   │
│  │                    │       │                            │   │
│  │ - Git worktree     │       │ - LakeBase API             │   │
│  │ - Local objects    │       │ - DB branching/versioning  │   │
│  │ - Shared refs      │       │ - Zero-copy at PG level    │   │
│  │ - Git-native ops   │       │ - Agent-friendly API       │   │
│  └────────────────────┘       └────────────────────────────┘   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐│
│  │ NullBackend (metadata only)                                ││
│  │ - COW only, no commits                                     ││
│  │ - No version history                                       ││
│  │ - Suitable for ephemeral workspaces                        ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Configuration:
```yaml
versioning:
  backend: lakebase | local | none
  lakebase:
    api_url: https://api.dbay.cloud:8443/api/v1
    database_id: db_xxx
    api_token: ${LAKEBASE_API_TOKEN}
```

### Virtual Workspace Types

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitMats Workspace Types                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────┐       ┌────────────────────────────┐   │
│  │ Inherited Workspace│       │ Standalone Workspace       │   │
│  │ (Git versioned)    │       │ (No Git in original)      │   │
│  │                    │       │                            │   │
│  │ Original has .git  │       │ Original has no .git      │   │
│  │ - Share git objects│       │ - Create isolated git     │   │
│  │ - Per-worktree HEAD│       │ - Own object store        │   │
│  │ - Shared refs      │       │ - Private commits         │   │
│  │ - Independent index│       │ - Never touch original    │   │
│  └────────────────────┘       └────────────────────────────┘   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐│
│  │ Database Workspace (LakeBase native)                       ││
│  │ - Original is a database branch                            ││
│  │ - No file symlinks - content in DB                         ││
│  │ - LakeBase provides zero-copy branching                    ││
│  │ - Schema + Data versioning                                 ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Properties

1. **Isolation**: Each virtual workspace is independent; modifications don't affect others
2. **Efficiency**: Zero disk overhead until first modification (symlinks)
3. **Git-native**: All operations use standard Git commands
4. **Traceability**: Full version history of changes in each workspace
5. **Safety**: Original workspace remains completely untouched

## Technology Stack

| Layer | Technology |
|-------|------------|
| Core Engine | Python 3.10+ / C (optional) |
| Git Integration | Git worktree + alternates + custom refs |
| Versioning Backend | Local Git (default) / LakeBase API (pluggable) / None (metadata only) |
| Storage | OverlayFS (Linux) / FUSE / App-level VFS |
| Metadata | SQLite + Git refs + LakeBase version API |
| CLI | gmt (standalone CLI, Git-style commands) |