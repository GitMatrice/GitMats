"""Tests for GitMats configuration management."""

from pathlib import Path
import tempfile

import pytest
import yaml

from gitmats.config import (
    GitMatsConfig,
    LocalGitConfig,
    LakeBaseConfig,
    NullBackendConfig,
    VersioningConfig,
    load_config,
)


class TestGitMatsConfig:
    """Tests for GitMatsConfig."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = GitMatsConfig()
        
        assert config.versioning.backend == "local"
        assert config.default_workspace_dir == "~/.gitmats/workspaces"
        assert config.default_hooks_enabled is True
    
    def test_config_paths(self):
        """Test path resolution."""
        config = GitMatsConfig()
        
        storage_path = config.get_storage_path()
        assert str(storage_path).endswith("workspaces")
        
        registry_path = config.get_registry_db_path()
        assert str(registry_path).endswith("registry.db")
    
    def test_config_to_yaml(self):
        """Test saving config to YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            
            config = GitMatsConfig()
            config.versioning.backend = "lakebase"
            config.versioning.lakebase.api_url = "https://api.example.com"
            config.versioning.lakebase.database_id = "db_test"
            
            config.to_yaml(config_path)
            
            assert config_path.exists()
            
            with open(config_path) as f:
                data = yaml.safe_load(f)
            
            assert data["versioning"]["backend"] == "lakebase"
    
    def test_config_from_yaml(self):
        """Test loading config from YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            
            config_data = {
                "versioning": {
                    "backend": "lakebase",
                    "lakebase": {
                        "api_url": "https://api.test.com",
                        "database_id": "db_abc",
                    },
                },
                "default_workspace_dir": "/custom/path",
            }
            
            with open(config_path, "w") as f:
                yaml.dump(config_data, f)
            
            config = GitMatsConfig.from_yaml(config_path)
            
            assert config.versioning.backend == "lakebase"
            assert config.versioning.lakebase.api_url == "https://api.test.com"
            assert config.default_workspace_dir == "/custom/path"
    
    def test_lakebase_api_token_from_env(self):
        """Test getting LakeBase API token from environment."""
        import os
        
        config = GitMatsConfig()
        config.versioning.lakebase.api_token = None
        
        # Test with environment variable
        os.environ["LAKEBASE_API_TOKEN"] = "test_token_from_env"
        token = config.get_lakebase_api_token()
        assert token == "test_token_from_env"
        
        # Cleanup
        del os.environ["LAKEBASE_API_TOKEN"]
    
    def test_lakebase_api_token_from_config(self):
        """Test getting LakeBase API token from config."""
        config = GitMatsConfig()
        config.versioning.lakebase.api_token = "test_token_from_config"
        
        token = config.get_lakebase_api_token()
        assert token == "test_token_from_config"


class TestLocalGitConfig:
    """Tests for LocalGitConfig."""
    
    def test_default_local_config(self):
        """Test default local Git config."""
        config = LocalGitConfig()
        
        assert config.shared_objects is True
        assert config.worktree_strategy == "linked"


class TestLakeBaseConfig:
    """Tests for LakeBaseConfig."""
    
    def test_default_lakebase_config(self):
        """Test default LakeBase config."""
        config = LakeBaseConfig()
        
        assert config.api_url is None
        assert config.branch_prefix == "gitmats-"
        assert config.parent_branch == "main"
    
    def test_custom_lakebase_config(self):
        """Test custom LakeBase config."""
        config = LakeBaseConfig(
            api_url="https://api.custom.com",
            database_id="db_xyz",
            branch_prefix="custom-",
        )
        
        assert config.api_url == "https://api.custom.com"
        assert config.database_id == "db_xyz"


class TestLoadConfig:
    """Tests for load_config function."""
    
    def test_load_default_when_no_file(self):
        """Test loading default config when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Point to non-existent path
            config_path = Path(tmpdir) / "nonexistent" / "config.yaml"
            config = load_config(config_path)
            
            assert config.versioning.backend == "local"
    
    def test_load_from_explicit_path(self):
        """Test loading from explicit path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            
            config_data = {
                "versioning": {"backend": "none"},
            }
            
            with open(config_path, "w") as f:
                yaml.dump(config_data, f)
            
            config = load_config(config_path)
            
            assert config.versioning.backend == "none"