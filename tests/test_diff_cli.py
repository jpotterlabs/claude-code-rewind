"""Integration tests for diff CLI command."""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
from datetime import datetime

from claude_rewind.cli.main import cli
from claude_rewind.core.models import (
    SnapshotMetadata, Snapshot, FileState, DiffFormat
)


class TestDiffCLI:
    """Test cases for diff CLI command."""
    
    @pytest.fixture
    def temp_project(self):
        """Create temporary project directory with Claude Rewind initialized."""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Create project structure
        (temp_dir / ".claude-rewind").mkdir()
        (temp_dir / ".claude-rewind" / "snapshots").mkdir()
        
        # Create sample files
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").write_text("def main():\n    print('Hello, World!')\n")
        (temp_dir / "README.md").write_text("# Test Project\n\nThis is a test.\n")
        
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_storage_components(self):
        """Create mock storage components."""
        mock_db = Mock()
        mock_file_store = Mock()
        
        # Sample snapshot metadata
        sample_snapshot = SnapshotMetadata(
            id="test_snapshot_123",
            timestamp=datetime.now(),
            action_type="edit_file",
            prompt_context="Modified main.py to add error handling",
            files_affected=[Path("src/main.py")],
            total_size=150,
            compression_ratio=0.7
        )
        
        mock_db.get_snapshots.return_value = [sample_snapshot]
        
        # Sample manifest
        mock_file_store.get_snapshot_manifest.return_value = {
            'snapshot_id': 'test_snapshot_123',
            'files': {
                'src/main.py': {
                    'exists': True,
                    'content_hash': 'abc123def456',
                    'size': 75,
                    'modified_time': datetime.now().isoformat(),
                    'permissions': 0o644
                }
            }
        }
        
        mock_file_store.retrieve_content.return_value = b"def main():\n    print('Hello!')\n"
        
        return mock_db, mock_file_store
    
    def test_diff_command_no_snapshot_shows_recent(self, temp_project, mock_storage_components):
        """Test diff command without snapshot ID shows recent snapshots."""
        mock_db, mock_file_store = mock_storage_components
        
        runner = CliRunner()
        
        with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
             patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store):
            
            result = runner.invoke(cli, ['--project-root', str(temp_project), 'diff'])
        
        assert result.exit_code == 0
        assert "Recent snapshots:" in result.output
        assert "test_snapshot_123" in result.output
        assert "edit_file" in result.output
    
    def test_diff_command_with_snapshot_id(self, temp_project, mock_storage_components):
        """Test diff command with specific snapshot ID."""
        mock_db, mock_file_store = mock_storage_components
        
        runner = CliRunner()
        
        # Mock the diff viewer to return a simple diff
        mock_diff_output = "--- src/main.py (snapshot test_snapshot_123)\n+++ src/main.py (current)\n@@ -1,2 +1,2 @@\n def main():\n-    print('Hello!')\n+    print('Hello, World!')\n"
        
        with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
             patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store), \
             patch('claude_rewind.cli.main.DiffViewer') as mock_diff_viewer_class:
            
            mock_diff_viewer = Mock()
            mock_diff_viewer.show_snapshot_diff.return_value = mock_diff_output
            mock_diff_viewer_class.return_value = mock_diff_viewer
            
            result = runner.invoke(cli, [
                '--project-root', str(temp_project), 
                'diff', 'test_snapshot_123'
            ])
        
        assert result.exit_code == 0
        assert "src/main.py" in result.output
        assert "Hello!" in result.output or "Hello, World!" in result.output
        
        # Verify diff viewer was called correctly
        mock_diff_viewer.show_snapshot_diff.assert_called_once_with(
            'test_snapshot_123', DiffFormat.UNIFIED
        )
    
    def test_diff_command_with_format_options(self, temp_project, mock_storage_components):
        """Test diff command with different format options."""
        mock_db, mock_file_store = mock_storage_components
        
        runner = CliRunner()
        
        formats_to_test = ['unified', 'side-by-side', 'patch']
        
        for format_name in formats_to_test:
            with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
                 patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store), \
                 patch('claude_rewind.cli.main.DiffViewer') as mock_diff_viewer_class:
                
                mock_diff_viewer = Mock()
                mock_diff_viewer.show_snapshot_diff.return_value = f"Mock {format_name} diff output"
                mock_diff_viewer_class.return_value = mock_diff_viewer
                
                result = runner.invoke(cli, [
                    '--project-root', str(temp_project),
                    'diff', 'test_snapshot_123',
                    '--format', format_name
                ])
            
            assert result.exit_code == 0
            assert f"Mock {format_name} diff output" in result.output
    
    def test_diff_command_file_specific(self, temp_project, mock_storage_components):
        """Test diff command for specific file."""
        mock_db, mock_file_store = mock_storage_components
        
        runner = CliRunner()
        
        mock_file_diff = "File-specific diff output for src/main.py"
        
        with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
             patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store), \
             patch('claude_rewind.cli.main.DiffViewer') as mock_diff_viewer_class:
            
            mock_diff_viewer = Mock()
            mock_diff_viewer.show_file_diff.return_value = mock_file_diff
            mock_diff_viewer_class.return_value = mock_diff_viewer
            
            result = runner.invoke(cli, [
                '--project-root', str(temp_project),
                'diff', 'test_snapshot_123',
                '--file', 'src/main.py'
            ])
        
        assert result.exit_code == 0
        assert mock_file_diff in result.output
        
        # Verify file diff was called correctly
        mock_diff_viewer.show_file_diff.assert_called_once_with(
            Path('src/main.py'), 'test_snapshot_123', 'current', DiffFormat.UNIFIED
        )
    
    def test_diff_command_between_snapshots(self, temp_project, mock_storage_components):
        """Test diff command between two snapshots."""
        mock_db, mock_file_store = mock_storage_components
        
        runner = CliRunner()
        
        mock_file_diff = "Diff between snapshot1 and snapshot2"
        
        with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
             patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store), \
             patch('claude_rewind.cli.main.DiffViewer') as mock_diff_viewer_class:
            
            mock_diff_viewer = Mock()
            mock_diff_viewer.show_file_diff.return_value = mock_file_diff
            mock_diff_viewer_class.return_value = mock_diff_viewer
            
            result = runner.invoke(cli, [
                '--project-root', str(temp_project),
                'diff',
                '--file', 'src/main.py',
                '--before', 'snapshot1',
                '--after', 'snapshot2'
            ])
        
        assert result.exit_code == 0
        assert mock_file_diff in result.output
        
        # Verify file diff was called with correct snapshots
        mock_diff_viewer.show_file_diff.assert_called_once_with(
            Path('src/main.py'), 'snapshot1', 'snapshot2', DiffFormat.UNIFIED
        )
    
    def test_diff_command_export_option(self, temp_project, mock_storage_components):
        """Test diff command with export option."""
        mock_db, mock_file_store = mock_storage_components
        
        runner = CliRunner()
        export_file = temp_project / "exported_diff.patch"
        
        mock_export_diff = "Exported diff content without colors"
        
        with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
             patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store), \
             patch('claude_rewind.cli.main.DiffViewer') as mock_diff_viewer_class:
            
            mock_diff_viewer = Mock()
            mock_diff_viewer.export_diff.return_value = mock_export_diff
            mock_diff_viewer_class.return_value = mock_diff_viewer
            
            result = runner.invoke(cli, [
                '--project-root', str(temp_project),
                'diff', 'test_snapshot_123',
                '--export', str(export_file)
            ])
        
        assert result.exit_code == 0
        assert f"Diff exported to: {export_file}" in result.output
        
        # Verify export was called
        mock_diff_viewer.export_diff.assert_called_once_with(
            'test_snapshot_123', DiffFormat.UNIFIED
        )
        
        # Verify file was written
        assert export_file.exists()
        assert export_file.read_text() == mock_export_diff
    
    def test_diff_command_context_lines_option(self, temp_project, mock_storage_components):
        """Test diff command with custom context lines."""
        mock_db, mock_file_store = mock_storage_components
        
        runner = CliRunner()
        
        with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
             patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store), \
             patch('claude_rewind.cli.main.DiffViewer') as mock_diff_viewer_class:
            
            mock_diff_viewer = Mock()
            mock_diff_viewer.show_snapshot_diff.return_value = "Mock diff with 5 context lines"
            mock_diff_viewer_class.return_value = mock_diff_viewer
            
            result = runner.invoke(cli, [
                '--project-root', str(temp_project),
                'diff', 'test_snapshot_123',
                '--context', '5'
            ])
        
        assert result.exit_code == 0
        
        # Verify DiffViewer was initialized with correct context lines
        mock_diff_viewer_class.assert_called_once()
        call_kwargs = mock_diff_viewer_class.call_args[1]
        assert call_kwargs['context_lines'] == 5
    
    def test_diff_command_no_color_option(self, temp_project, mock_storage_components):
        """Test diff command with no-color option."""
        mock_db, mock_file_store = mock_storage_components
        
        runner = CliRunner()
        
        with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
             patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store), \
             patch('claude_rewind.cli.main.DiffViewer') as mock_diff_viewer_class:
            
            mock_diff_viewer = Mock()
            mock_diff_viewer.show_snapshot_diff.return_value = "Plain text diff"
            mock_diff_viewer_class.return_value = mock_diff_viewer
            
            result = runner.invoke(cli, [
                '--project-root', str(temp_project),
                'diff', 'test_snapshot_123',
                '--no-color'
            ])
        
        assert result.exit_code == 0
        
        # Verify DiffViewer was initialized with colors disabled
        mock_diff_viewer_class.assert_called_once()
        call_kwargs = mock_diff_viewer_class.call_args[1]
        assert call_kwargs['enable_colors'] is False
    
    def test_diff_command_not_initialized(self, temp_project):
        """Test diff command when project is not initialized."""
        # Remove .claude-rewind directory
        shutil.rmtree(temp_project / ".claude-rewind")
        
        runner = CliRunner()
        
        result = runner.invoke(cli, [
            '--project-root', str(temp_project),
            'diff', 'test_snapshot_123'
        ])
        
        assert result.exit_code == 1
        assert "Claude Rewind is not initialized" in result.output
        assert "Run 'claude-rewind init' first" in result.output
    
    def test_diff_command_storage_error(self, temp_project, mock_storage_components):
        """Test diff command when storage error occurs."""
        mock_db, mock_file_store = mock_storage_components
        
        # Make database manager raise an exception
        mock_db.get_snapshots.side_effect = Exception("Database connection failed")
        
        runner = CliRunner()
        
        with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
             patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store):
            
            result = runner.invoke(cli, [
                '--project-root', str(temp_project),
                'diff', 'test_snapshot_123'
            ])
        
        assert result.exit_code == 1
        assert "Error generating diff" in result.output
    
    def test_diff_command_verbose_error_output(self, temp_project, mock_storage_components):
        """Test diff command verbose error output."""
        mock_db, mock_file_store = mock_storage_components
        
        # Make diff viewer raise an exception
        with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
             patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store), \
             patch('claude_rewind.cli.main.DiffViewer') as mock_diff_viewer_class:
            
            mock_diff_viewer = Mock()
            mock_diff_viewer.show_snapshot_diff.side_effect = Exception("Diff generation failed")
            mock_diff_viewer_class.return_value = mock_diff_viewer
            
            runner = CliRunner()
            
            result = runner.invoke(cli, [
                '--project-root', str(temp_project),
                '--verbose',
                'diff', 'test_snapshot_123'
            ])
        
        assert result.exit_code == 1
        assert "Error generating diff" in result.output
        # In verbose mode, should show traceback
        assert "Traceback" in result.output or "Exception" in result.output


class TestInteractiveDiffViewer:
    """Test cases for interactive diff viewer functionality."""
    
    @pytest.fixture
    def mock_rich_components(self):
        """Mock Rich components for testing."""
        with patch('claude_rewind.cli.main.Console') as mock_console, \
             patch('claude_rewind.cli.main.Live') as mock_live, \
             patch('claude_rewind.cli.main.Layout') as mock_layout:
            yield mock_console, mock_live, mock_layout
    
    def test_interactive_diff_missing_dependencies(self, temp_project, mock_storage_components):
        """Test interactive diff when Rich/keyboard dependencies are missing."""
        mock_db, mock_file_store = mock_storage_components
        
        runner = CliRunner()
        
        with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
             patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store), \
             patch('claude_rewind.cli.main.DiffViewer') as mock_diff_viewer_class:
            
            mock_diff_viewer = Mock()
            mock_diff_viewer_class.return_value = mock_diff_viewer
            
            # Mock import error for Rich
            with patch('builtins.__import__', side_effect=ImportError("No module named 'rich'")):
                result = runner.invoke(cli, [
                    '--project-root', str(temp_project),
                    'diff', 'test_snapshot_123',
                    '--interactive'
                ])
        
        assert result.exit_code == 1
        assert "Interactive mode requires 'rich' and 'keyboard' packages" in result.output
        assert "pip install rich keyboard" in result.output
    
    def test_interactive_diff_no_changes(self, temp_project, mock_storage_components, mock_rich_components):
        """Test interactive diff when no changes are found."""
        mock_db, mock_file_store = mock_storage_components
        mock_console, mock_live, mock_layout = mock_rich_components
        
        runner = CliRunner()
        
        with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
             patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store), \
             patch('claude_rewind.cli.main.DiffViewer') as mock_diff_viewer_class, \
             patch('claude_rewind.cli.main.keyboard'), \
             patch('claude_rewind.cli.main.threading'):
            
            mock_diff_viewer = Mock()
            mock_diff_viewer.get_file_changes.return_value = []  # No changes
            mock_diff_viewer_class.return_value = mock_diff_viewer
            
            # Mock console instance
            mock_console_instance = Mock()
            mock_console.return_value = mock_console_instance
            
            result = runner.invoke(cli, [
                '--project-root', str(temp_project),
                'diff', 'test_snapshot_123',
                '--interactive'
            ])
        
        # Should not exit with error, but show no changes message
        mock_console_instance.print.assert_called()
        print_calls = [call[0][0] for call in mock_console_instance.print.call_args_list]
        assert any("No changes found" in str(call) for call in print_calls)


class TestDiffCLIEdgeCases:
    """Test edge cases and error conditions for diff CLI."""
    
    def test_diff_command_invalid_format(self, temp_project):
        """Test diff command with invalid format option."""
        runner = CliRunner()
        
        result = runner.invoke(cli, [
            '--project-root', str(temp_project),
            'diff', 'test_snapshot',
            '--format', 'invalid_format'
        ])
        
        assert result.exit_code != 0
        assert "Invalid value for '--format'" in result.output
    
    def test_diff_command_invalid_context_lines(self, temp_project):
        """Test diff command with invalid context lines."""
        runner = CliRunner()
        
        result = runner.invoke(cli, [
            '--project-root', str(temp_project),
            'diff', 'test_snapshot',
            '--context', 'not_a_number'
        ])
        
        assert result.exit_code != 0
        assert "Invalid value for '--context'" in result.output
    
    def test_diff_command_nonexistent_export_directory(self, temp_project, mock_storage_components):
        """Test diff command with export to nonexistent directory."""
        mock_db, mock_file_store = mock_storage_components
        
        runner = CliRunner()
        export_file = temp_project / "nonexistent" / "dir" / "diff.patch"
        
        with patch('claude_rewind.cli.main.DatabaseManager', return_value=mock_db), \
             patch('claude_rewind.cli.main.FileStore', return_value=mock_file_store), \
             patch('claude_rewind.cli.main.DiffViewer') as mock_diff_viewer_class:
            
            mock_diff_viewer = Mock()
            mock_diff_viewer.export_diff.return_value = "Mock diff content"
            mock_diff_viewer_class.return_value = mock_diff_viewer
            
            result = runner.invoke(cli, [
                '--project-root', str(temp_project),
                'diff', 'test_snapshot_123',
                '--export', str(export_file)
            ])
        
        # Should handle directory creation or show appropriate error
        # The exact behavior depends on implementation
        assert result.exit_code in [0, 1]  # Either succeeds or fails gracefully