"""Tests for configuration management."""

import pytest
import tempfile
from pathlib import Path
from claude_rewind.core.config import ConfigManager, RewindConfig


class TestConfigManager:
    """Test cases for ConfigManager."""
    
    def test_default_config_creation(self):
        """Test that default configuration is created correctly."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_manager = ConfigManager(project_root)
            
            default_config = config_manager.get_default_config()
            
            assert 'storage' in default_config
            assert 'display' in default_config
            assert 'hooks' in default_config
            assert 'git_integration' in default_config
            assert 'performance' in default_config
            
            # Test specific default values
            assert default_config['storage']['max_snapshots'] == 100
            assert default_config['storage']['compression_enabled'] is True
            assert default_config['display']['theme'] == 'dark'
            assert default_config['git_integration']['respect_gitignore'] is True
    
    def test_config_validation(self):
        """Test configuration validation."""
        config_manager = ConfigManager()
        
        # Valid config should pass
        valid_config = config_manager.get_default_config()
        errors = config_manager.validate_config(valid_config)
        assert len(errors) == 0
        
        # Invalid config should fail
        invalid_config = {
            'storage': {'max_snapshots': -1},
            'display': {'theme': 'invalid_theme'},
            'performance': {'max_file_size_mb': 0}
        }
        errors = config_manager.validate_config(invalid_config)
        assert len(errors) > 0
        assert any('max_snapshots must be greater than 0' in error for error in errors)
        assert any('theme must be' in error for error in errors)
    
    def test_config_file_operations(self):
        """Test saving and loading configuration files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_manager = ConfigManager(project_root)
            
            # Create default config file
            assert config_manager.create_default_config_file() is True
            assert config_manager.get_config_path().exists()
            
            # Load the config back
            loaded_config = config_manager.load_config()
            default_config = config_manager.get_default_config()
            
            assert loaded_config == default_config


class TestRewindConfig:
    """Test cases for RewindConfig dataclass."""
    
    def test_config_initialization(self):
        """Test that RewindConfig initializes with correct defaults."""
        config = RewindConfig()
        
        assert config.storage.max_snapshots == 100
        assert config.storage.compression_enabled is True
        assert config.display.theme == 'dark'
        assert config.hooks.claude_integration_enabled is True
        assert config.git_integration.respect_gitignore is True
        assert config.performance.max_file_size_mb == 100