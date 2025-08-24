"""Tests for rollback CLI commands."""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from datetime import datetime
from click.testing import CliRunner

from claude_rewind.cli.main import cli
from claude_rewind.storage.database import DatabaseManager
from claude_rewind.storage.file_store import FileStore
from claude_rewind.core.models import SnapshotMetadata


class TestRollbackCLI:
    """Test cases for rollback CLI commands."""
    
    @pytest.fixture
    def temp_project(self):
        """Create a temporary project with Claude Rewind initialized."""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Create project structure
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").write_text("print('hello')")
        (temp_dir / "src" / "utils.py").write_text("def helper(): pass")
        (temp_dir / "README.md").write_text("# Test Project")
        
        # Initialize Claude Rewind
        rewind_dir = temp_dir / ".claude-rewind"
        rewind_dir.mkdir()
        (rewind_dir / "snapshots").mkdir()
        (rewind_dir / "backups").mkdir()
        
        # Create config file
        config_data = {
            "storage": {
                "max_snapshots": 100,
                "compression_enabled": True,
                "cleanup_after_days": 30,
                "max_disk_usage_mb": 1000
            },
            "display": {
                "theme": "dark",
                "diff_algorithm": "unified",
                "show_line_numbers": True,
                "context_lines": 3
            },
            "git_integration": {
                "respect_gitignore": True,
                "auto_commit_rollbacks": False
            }
        }
        
        import yaml
        with open(rewind_dir / "config.yml", 'w') as f:
            yaml.dump(config_data, f)
        
        # Create status file
        status_data = {
            "initialized_at": datetime.now().isoformat(),
            "version": "0.1.0",
            "project_root": str(temp_dir),
            "git_integration": False
        }
        
        with open(rewind_dir / "status.json", 'w') as f:
            json.dump(status_data, f, indent=2)
        
        # Initialize database
        db_manager = DatabaseManager(rewind_dir / "metadata.db")
        
        # Create a test snapshot
        snapshot_metadata = SnapshotMetadata(
            id="test_snapshot_001",
            timestamp=datetime.now(),
            action_type="edit_file",
            prompt_context="Test snapshot for rollback",
            files_affected=[Path("src/main.py")],
            total_size=100,
            compression_ratio=0.8
        )
        
        db_manager.create_snapshot(snapshot_metadata)
        
        # Create file store and snapshot
        file_store = FileStore(rewind_dir)
        
        # Create snapshot manifest
        manifest = {
            'snapshot_id': 'test_snapshot_001',
            'created_at': datetime.now().isoformat(),
            'file_count': 3,
            'files': {
                'src/main.py': {
                    'exists': True,
                    'content_hash': 'abc123',
                    'size': 15,
                    'modified_time': datetime.now().isoformat(),
                    'permissions': 0o644
                },
                'src/utils.py': {
                    'exists': True,
                    'content_hash': 'def456',
                    'size': 20,
                    'modified_time': datetime.now().isoformat(),
                    'permissions': 0o644
                },
                'README.md': {
                    'exists': True,
                    'content_hash': 'ghi789',
                    'size': 15,
                    'modified_time': datetime.now().isoformat(),
                    'permissions': 0o644
                }
            },
            'total_size': 50,
            'compressed_size': 40
        }
        
        # Create snapshot directory and manifest
        snapshot_dir = rewind_dir / "snapshots" / "test_snapshot_001"
        snapshot_dir.mkdir()
        with open(snapshot_dir / "manifest.json", 'w') as f:
            json.dump(manifest, f, indent=2)
        
        # Store file content
        file_store.store_content(b"print('hello')")  # For main.py
        file_store.store_content(b"def helper(): pass")  # For utils.py
        file_store.store_content(b"# Test Project")  # For README.md
        
        yield temp_dir
        
        # Cleanup
        shutil.rmtree(temp_dir)
    
    def test_preview_command_basic(self, temp_project):
        """Test basic preview command functionality."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            # Change to project directory
            import os
            os.chdir(str(temp_project))
            
            result = runner.invoke(cli, ['preview', 'test_snapshot_001'])
            
            assert result.exit_code == 0
            assert "Rollback Preview for Snapshot: test_snapshot_001" in result.output
            assert "Summary:" in result.output
            assert "Files to restore:" in result.output or "Files to delete:" in result.output
    
    def test_preview_command_detailed(self, temp_project):
        """Test preview command with detailed flag."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            import os
            os.chdir(str(temp_project))
            
            result = runner.invoke(cli, ['preview', 'test_snapshot_001', '--detailed'])
            
            assert result.exit_code == 0
            assert "Rollback Preview for Snapshot: test_snapshot_001" in result.output
            assert "Summary:" in result.output
    
    def test_preview_command_selective_files(self, temp_project):
        """Test preview command with selective files."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            import os
            os.chdir(str(temp_project))
            
            result = runner.invoke(cli, [
                'preview', 'test_snapshot_001', 
                '--files', 'src/main.py'
            ])
            
            assert result.exit_code == 0
            assert "Rollback Preview for Snapshot: test_snapshot_001" in result.output
    
    def test_preview_command_nonexistent_snapshot(self, temp_project):
        """Test preview command with non-existent snapshot."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            import os
            os.chdir(str(temp_project))
            
            result = runner.invoke(cli, ['preview', 'nonexistent_snapshot'])
            
            assert result.exit_code == 1
            assert "Snapshot not found" in result.output
    
    def test_rollback_command_dry_run(self, temp_project):
        """Test rollback command in dry run mode."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            import os
            os.chdir(str(temp_project))
            
            result = runner.invoke(cli, [
                'rollback', 'test_snapshot_001', 
                '--dry-run'
            ])
            
            assert result.exit_code == 0
            assert "Analyzing rollback to snapshot: test_snapshot_001" in result.output
            assert "[DRY RUN] No actual changes would be made." in result.output
    
    def test_rollback_command_with_force(self, temp_project):
        """Test rollback command with force flag."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            import os
            os.chdir(str(temp_project))
            
            # Modify a file to create a difference
            (temp_project / "src" / "main.py").write_text("print('modified')")
            
            result = runner.invoke(cli, [
                'rollback', 'test_snapshot_001', 
                '--force', '--no-backup'
            ])
            
            # Should complete without asking for confirmation
            assert result.exit_code == 0
            assert "Analyzing rollback to snapshot: test_snapshot_001" in result.output
            assert "Executing rollback..." in result.output
    
    def test_rollback_command_selective_files(self, temp_project):
        """Test rollback command with selective files."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            import os
            os.chdir(str(temp_project))
            
            result = runner.invoke(cli, [
                'rollback', 'test_snapshot_001',
                '--files', 'src/main.py',
                '--force', '--no-backup'
            ])
            
            assert result.exit_code == 0
            assert "Analyzing rollback to snapshot: test_snapshot_001" in result.output
    
    def test_rollback_command_not_initialized(self):
        """Test rollback command when project is not initialized."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ['rollback', 'test_snapshot'])
            
            assert result.exit_code == 1
            assert "Claude Rewind is not initialized" in result.output
            assert "Run 'claude-rewind init' first" in result.output
    
    def test_preview_command_not_initialized(self):
        """Test preview command when project is not initialized."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ['preview', 'test_snapshot'])
            
            assert result.exit_code == 1
            assert "Claude Rewind is not initialized" in result.output
            assert "Run 'claude-rewind init' first" in result.output
    
    def test_rollback_command_preserve_changes_flag(self, temp_project):
        """Test rollback command with preserve changes flag."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            import os
            os.chdir(str(temp_project))
            
            result = runner.invoke(cli, [
                'rollback', 'test_snapshot_001',
                '--preserve-changes',
                '--force', '--dry-run'
            ])
            
            assert result.exit_code == 0
            assert "Analyzing rollback to snapshot: test_snapshot_001" in result.output
    
    def test_rollback_command_no_preserve_changes(self, temp_project):
        """Test rollback command without preserving changes."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            import os
            os.chdir(str(temp_project))
            
            result = runner.invoke(cli, [
                'rollback', 'test_snapshot_001',
                '--no-preserve-changes',
                '--force', '--dry-run'
            ])
            
            assert result.exit_code == 0
            assert "Analyzing rollback to snapshot: test_snapshot_001" in result.output


class TestRollbackCLIHelp:
    """Test help and usage information for rollback commands."""
    
    def test_rollback_help(self):
        """Test rollback command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['rollback', '--help'])
        
        assert result.exit_code == 0
        assert "Rollback project state to a specific snapshot" in result.output
        assert "--files" in result.output
        assert "--preserve-changes" in result.output
        assert "--dry-run" in result.output
        assert "--force" in result.output
    
    def test_preview_help(self):
        """Test preview command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ['preview', '--help'])
        
        assert result.exit_code == 0
        assert "Preview what a rollback operation would do" in result.output
        assert "--files" in result.output
        assert "--preserve-changes" in result.output
        assert "--detailed" in result.output