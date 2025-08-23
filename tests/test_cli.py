"""Integration tests for CLI functionality."""

import pytest
import tempfile
import shutil
from pathlib import Path
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from claude_rewind.cli.main import cli
from claude_rewind.core.config import ConfigManager


class TestCLIInitialization:
    """Test CLI initialization and basic functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_cli_help(self):
        """Test that CLI help works."""
        result = self.runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'Claude Rewind Tool' in result.output
        assert 'Time-travel debugging' in result.output
    
    def test_cli_version_info(self):
        """Test CLI shows version and basic info."""
        result = self.runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'init' in result.output
        assert 'status' in result.output
        assert 'cleanup' in result.output
    
    def test_cli_with_verbose_flag(self):
        """Test CLI with verbose flag."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['--verbose', 'status'])
            # Should not fail even if not initialized
            assert result.exit_code == 0
    
    def test_cli_with_custom_project_root(self):
        """Test CLI with custom project root."""
        result = self.runner.invoke(cli, ['--project-root', str(self.temp_dir), 'status'])
        assert result.exit_code == 0
    
    def test_cli_with_invalid_config_path(self):
        """Test CLI with invalid config path."""
        result = self.runner.invoke(cli, ['--config', '/nonexistent/config.yml', 'status'])
        # Should fail because config file doesn't exist
        assert result.exit_code != 0


class TestInitCommand:
    """Test the init command functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_init_command_basic(self):
        """Test basic init command functionality."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['init'])
            assert result.exit_code == 0
            assert 'Initializing Claude Rewind' in result.output
            assert 'initialized successfully' in result.output
            
            # Check that directories and files were created
            assert Path('.claude-rewind').exists()
            assert Path('.claude-rewind/snapshots').exists()
            assert Path('.claude-rewind/config.yml').exists()
            assert Path('.claude-rewind/metadata.db').exists()
            assert Path('.claude-rewind/status.json').exists()
    
    def test_init_command_with_custom_root(self):
        """Test init command with custom project root."""
        result = self.runner.invoke(cli, ['--project-root', str(self.temp_dir), 'init'])
        assert result.exit_code == 0
        
        # Check that directories were created in custom location
        rewind_dir = self.temp_dir / '.claude-rewind'
        assert rewind_dir.exists()
        assert (rewind_dir / 'snapshots').exists()
        assert (rewind_dir / 'config.yml').exists()
        assert (rewind_dir / 'metadata.db').exists()
        assert (rewind_dir / 'status.json').exists()
    
    def test_init_command_already_initialized(self):
        """Test init command when already initialized."""
        with self.runner.isolated_filesystem():
            # Initialize once
            result1 = self.runner.invoke(cli, ['init'])
            assert result1.exit_code == 0
            
            # Initialize again - should show already initialized message
            result2 = self.runner.invoke(cli, ['init'])
            assert result2.exit_code == 0
            assert 'already initialized' in result2.output
    
    def test_init_command_force_reinitialize(self):
        """Test init command with force flag to reinitialize."""
        with self.runner.isolated_filesystem():
            # Initialize once
            result1 = self.runner.invoke(cli, ['init'])
            assert result1.exit_code == 0
            
            # Force reinitialize
            result2 = self.runner.invoke(cli, ['init', '--force'])
            assert result2.exit_code == 0
            assert 'initialized successfully' in result2.output
    
    def test_init_creates_valid_config(self):
        """Test that init creates a valid configuration file."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['init'])
            assert result.exit_code == 0
            
            # Validate the created config
            config_manager = ConfigManager(Path.cwd())
            config_data = config_manager.load_config()
            validation_errors = config_manager.validate_config(config_data)
            assert len(validation_errors) == 0
    
    def test_init_creates_database(self):
        """Test that init creates and initializes the database."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['init'])
            assert result.exit_code == 0
            assert 'Initialized database' in result.output
            
            # Check database file exists
            db_path = Path('.claude-rewind/metadata.db')
            assert db_path.exists()
            
            # Verify database has correct tables
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Check snapshots table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='snapshots'")
            assert cursor.fetchone() is not None
            
            # Check file_changes table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='file_changes'")
            assert cursor.fetchone() is not None
            
            conn.close()
    
    def test_init_creates_status_file(self):
        """Test that init creates a status file with correct information."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['init'])
            assert result.exit_code == 0
            
            # Check status file exists and has correct content
            status_file = Path('.claude-rewind/status.json')
            assert status_file.exists()
            
            import json
            with open(status_file) as f:
                status_data = json.load(f)
            
            assert 'initialized_at' in status_data
            assert 'version' in status_data
            assert 'project_root' in status_data
            assert 'git_integration' in status_data
    
    def test_init_verbose_mode(self):
        """Test init command with verbose flag."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['--verbose', 'init'])
            assert result.exit_code == 0
            assert 'Created directory:' in result.output
            assert 'Created snapshots directory:' in result.output
            assert 'Created snapshots table' in result.output
    
    def test_init_skip_git_check(self):
        """Test init command with skip git check flag."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['init', '--skip-git-check'])
            assert result.exit_code == 0
            assert 'initialized successfully' in result.output
            
            # Check status file reflects git integration was skipped
            status_file = Path('.claude-rewind/status.json')
            import json
            with open(status_file) as f:
                status_data = json.load(f)
            assert status_data['git_integration'] is False
    
    @patch('git.Repo')
    def test_init_with_git_repository(self, mock_repo):
        """Test init command in a git repository."""
        with self.runner.isolated_filesystem():
            # Mock git repository
            mock_repo_instance = MagicMock()
            mock_repo_instance.working_dir = str(Path.cwd())
            mock_repo.return_value = mock_repo_instance
            
            result = self.runner.invoke(cli, ['--verbose', 'init'])
            assert result.exit_code == 0
            assert 'Detected git repository' in result.output
            assert 'Created .gitignore' in result.output or 'Added .claude-rewind/ to .gitignore' in result.output
    
    @patch('git.Repo')
    def test_init_with_existing_gitignore(self, mock_repo):
        """Test init command with existing .gitignore file."""
        with self.runner.isolated_filesystem():
            # Create existing .gitignore
            with open('.gitignore', 'w') as f:
                f.write("*.pyc\n__pycache__/\n")
            
            # Mock git repository
            mock_repo_instance = MagicMock()
            mock_repo_instance.working_dir = str(Path.cwd())
            mock_repo.return_value = mock_repo_instance
            
            result = self.runner.invoke(cli, ['init'])
            assert result.exit_code == 0
            assert 'Added .claude-rewind/ to .gitignore' in result.output
            
            # Check .gitignore was updated
            with open('.gitignore') as f:
                content = f.read()
            assert '.claude-rewind/' in content
    
    @patch('git.Repo')
    def test_init_git_repository_error(self, mock_repo):
        """Test init command handles git repository errors gracefully."""
        with self.runner.isolated_filesystem():
            # Mock git repository error
            mock_repo.side_effect = Exception("Git error")
            
            result = self.runner.invoke(cli, ['--verbose', 'init'])
            assert result.exit_code == 0  # Should still succeed
            assert 'Git integration warning' in result.output
            assert 'initialized successfully' in result.output


class TestStatusCommand:
    """Test the status command functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        
    def test_status_not_initialized(self):
        """Test status command when not initialized."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['status'])
            assert result.exit_code == 0
            assert 'Not initialized' in result.output
            assert 'claude-rewind init' in result.output
    
    def test_status_initialized(self):
        """Test status command when initialized."""
        with self.runner.isolated_filesystem():
            # Initialize first
            init_result = self.runner.invoke(cli, ['init'])
            assert init_result.exit_code == 0
            
            # Check status
            result = self.runner.invoke(cli, ['status'])
            assert result.exit_code == 0
            assert 'Status: Initialized' in result.output
            assert 'Configuration:' in result.output
            assert 'Max snapshots:' in result.output
            assert 'Compression:' in result.output
    
    def test_status_shows_config_info(self):
        """Test that status shows configuration information."""
        with self.runner.isolated_filesystem():
            # Initialize first
            self.runner.invoke(cli, ['init'])
            
            # Check status
            result = self.runner.invoke(cli, ['status'])
            assert result.exit_code == 0
            assert 'Max snapshots: 100' in result.output  # Default value
            assert 'Compression: Enabled' in result.output  # Default value


class TestCleanupCommand:
    """Test the cleanup command functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        
    def test_cleanup_not_initialized(self):
        """Test cleanup command when not initialized."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(cli, ['cleanup'])
            assert result.exit_code == 1
            assert 'not initialized' in result.output
    
    def test_cleanup_dry_run(self):
        """Test cleanup command with dry run."""
        with self.runner.isolated_filesystem():
            # Initialize first
            self.runner.invoke(cli, ['init'])
            
            # Run cleanup with dry run
            result = self.runner.invoke(cli, ['cleanup', '--dry-run'])
            assert result.exit_code == 0
            assert 'Dry run:' in result.output
            assert 'Would clean up' in result.output
    
    def test_cleanup_with_force(self):
        """Test cleanup command with force flag."""
        with self.runner.isolated_filesystem():
            # Initialize first
            self.runner.invoke(cli, ['init'])
            
            # Run cleanup with force
            result = self.runner.invoke(cli, ['cleanup', '--force'])
            assert result.exit_code == 0
            # Should not ask for confirmation
            assert 'Clean up snapshots' not in result.output
    
    def test_cleanup_interactive_cancel(self):
        """Test cleanup command interactive cancellation."""
        with self.runner.isolated_filesystem():
            # Initialize first
            self.runner.invoke(cli, ['init'])
            
            # Run cleanup and cancel
            result = self.runner.invoke(cli, ['cleanup'], input='n\n')
            assert result.exit_code == 0
            assert 'Cleanup cancelled' in result.output


class TestConfigCommand:
    """Test the config command functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        
    def test_config_command_shows_settings(self):
        """Test that config command shows current settings."""
        with self.runner.isolated_filesystem():
            # Initialize first
            self.runner.invoke(cli, ['init'])
            
            # Show config
            result = self.runner.invoke(cli, ['config'])
            assert result.exit_code == 0
            assert 'Configuration file:' in result.output
            assert 'Current configuration:' in result.output
            assert 'Storage:' in result.output
            assert 'Display:' in result.output
            assert 'Git Integration:' in result.output
    
    def test_config_shows_default_values(self):
        """Test that config shows expected default values."""
        with self.runner.isolated_filesystem():
            # Initialize first
            self.runner.invoke(cli, ['init'])
            
            # Show config
            result = self.runner.invoke(cli, ['config'])
            assert result.exit_code == 0
            assert 'Max snapshots: 100' in result.output
            assert 'Compression: Enabled' in result.output
            assert 'Theme: dark' in result.output
            assert 'Respect .gitignore: True' in result.output


class TestValidateCommand:
    """Test the validate command functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        
    def test_validate_valid_config(self):
        """Test validate command with valid configuration."""
        with self.runner.isolated_filesystem():
            # Initialize first
            self.runner.invoke(cli, ['init'])
            
            # Validate config
            result = self.runner.invoke(cli, ['validate'])
            assert result.exit_code == 0
            assert 'Configuration is valid' in result.output
    
    def test_validate_only_flag(self):
        """Test validate command with --validate-only flag."""
        with self.runner.isolated_filesystem():
            # Initialize first
            self.runner.invoke(cli, ['init'])
            
            # Validate config with flag
            result = self.runner.invoke(cli, ['validate', '--validate-only'])
            assert result.exit_code == 0
            assert 'Configuration is valid' in result.output
            # Should not show additional details
            assert 'Configuration file:' not in result.output
    
    def test_validate_invalid_config(self):
        """Test validate command with invalid configuration."""
        with self.runner.isolated_filesystem():
            # Initialize first
            self.runner.invoke(cli, ['init'])
            
            # Create invalid config
            config_path = Path('.claude-rewind/config.yml')
            with open(config_path, 'w') as f:
                f.write("""
storage:
  max_snapshots: -1  # Invalid value
  max_disk_usage_mb: 0  # Invalid value
""")
            
            # Validate config
            result = self.runner.invoke(cli, ['validate'])
            assert result.exit_code == 1
            assert 'Configuration validation errors' in result.output
            assert 'max_snapshots must be greater than 0' in result.output


class TestCLIErrorHandling:
    """Test CLI error handling scenarios."""
    
    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
    
    def test_cli_with_invalid_project_root(self):
        """Test CLI with invalid project root."""
        result = self.runner.invoke(cli, ['--project-root', '/nonexistent/path', 'status'])
        # Should fail because path doesn't exist
        assert result.exit_code != 0
    
    def test_cli_handles_config_loading_errors(self):
        """Test CLI handles configuration loading errors gracefully."""
        with self.runner.isolated_filesystem():
            # Create invalid YAML config
            Path('.claude-rewind').mkdir()
            with open('.claude-rewind/config.yml', 'w') as f:
                f.write('invalid: yaml: content: [')
            
            # Should fall back to default config
            result = self.runner.invoke(cli, ['--verbose', 'status'])
            assert result.exit_code == 0
    
    def test_cli_resilient_parsing(self):
        """Test CLI resilient parsing for help and completion."""
        # This tests that configuration errors don't prevent help from working
        with patch('claude_rewind.core.config.ConfigManager.load_config') as mock_load:
            mock_load.side_effect = Exception("Config error")
            
            result = self.runner.invoke(cli, ['--help'])
            assert result.exit_code == 0
            assert 'Claude Rewind Tool' in result.output


class TestCLIIntegration:
    """Test CLI integration scenarios."""
    
    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
    
    def test_full_workflow_init_status_cleanup(self):
        """Test complete workflow: init -> status -> cleanup."""
        with self.runner.isolated_filesystem():
            # Initialize
            init_result = self.runner.invoke(cli, ['init'])
            assert init_result.exit_code == 0
            
            # Check status
            status_result = self.runner.invoke(cli, ['status'])
            assert status_result.exit_code == 0
            assert 'Status: Initialized' in status_result.output
            
            # Run cleanup (dry run)
            cleanup_result = self.runner.invoke(cli, ['cleanup', '--dry-run'])
            assert cleanup_result.exit_code == 0
            assert 'Dry run:' in cleanup_result.output
    
    def test_config_validation_workflow(self):
        """Test configuration and validation workflow."""
        with self.runner.isolated_filesystem():
            # Initialize
            self.runner.invoke(cli, ['init'])
            
            # Show config
            config_result = self.runner.invoke(cli, ['config'])
            assert config_result.exit_code == 0
            
            # Validate config
            validate_result = self.runner.invoke(cli, ['validate'])
            assert validate_result.exit_code == 0
            assert 'Configuration is valid' in validate_result.output
    
    def test_verbose_mode_provides_extra_info(self):
        """Test that verbose mode provides additional information."""
        with self.runner.isolated_filesystem():
            # Initialize
            self.runner.invoke(cli, ['init'])
            
            # Run cleanup with verbose (not dry run to see verbose output)
            result = self.runner.invoke(cli, ['--verbose', 'cleanup', '--force'])
            assert result.exit_code == 0
            # Verbose mode should show configuration details
            assert 'Configuration: max_snapshots=' in result.output