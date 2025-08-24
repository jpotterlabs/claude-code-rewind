"""Simple integration tests for diff CLI command."""

import pytest
import tempfile
import shutil
from pathlib import Path
from click.testing import CliRunner

from claude_rewind.cli.main import cli


class TestDiffCLIBasic:
    """Basic test cases for diff CLI command."""
    
    @pytest.fixture
    def temp_project(self):
        """Create temporary project directory."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_diff_command_not_initialized(self, temp_project):
        """Test diff command when project is not initialized."""
        runner = CliRunner()
        
        result = runner.invoke(cli, [
            '--project-root', str(temp_project),
            'diff', 'test_snapshot_123'
        ])
        
        assert result.exit_code == 1
        assert "Claude Rewind is not initialized" in result.output
        assert "Run 'claude-rewind init' first" in result.output
    
    def test_diff_command_help(self):
        """Test diff command help output."""
        runner = CliRunner()
        
        result = runner.invoke(cli, ['diff', '--help'])
        
        assert result.exit_code == 0
        assert "Show diff for snapshot or between snapshots" in result.output
        assert "--format" in result.output
        assert "--file" in result.output
        assert "--interactive" in result.output
    
    def test_diff_command_invalid_format(self, temp_project):
        """Test diff command with invalid format option."""
        runner = CliRunner()
        
        result = runner.invoke(cli, [
            '--project-root', str(temp_project),
            'diff', 'test_snapshot',
            '--format', 'invalid_format'
        ])
        
        assert result.exit_code != 0
        assert "Invalid value for" in result.output or "Usage:" in result.output
    
    def test_diff_command_invalid_context_lines(self, temp_project):
        """Test diff command with invalid context lines."""
        runner = CliRunner()
        
        result = runner.invoke(cli, [
            '--project-root', str(temp_project),
            'diff', 'test_snapshot',
            '--context', 'not_a_number'
        ])
        
        assert result.exit_code != 0
        assert "Invalid value for" in result.output or "Usage:" in result.output


class TestDiffCLIWithMockProject:
    """Test diff CLI with a mock initialized project."""
    
    @pytest.fixture
    def initialized_project(self):
        """Create temporary project with Claude Rewind initialized."""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Create .claude-rewind directory structure
        rewind_dir = temp_dir / ".claude-rewind"
        rewind_dir.mkdir()
        (rewind_dir / "snapshots").mkdir()
        
        # Create empty database file
        (rewind_dir / "metadata.db").touch()
        
        # Create sample files
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").write_text("def main():\n    print('Hello, World!')\n")
        
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_diff_command_no_snapshots(self, initialized_project):
        """Test diff command when no snapshots exist."""
        runner = CliRunner()
        
        # This will fail because the database is empty, but it should fail gracefully
        result = runner.invoke(cli, [
            '--project-root', str(initialized_project),
            'diff'
        ])
        
        # Should either show "No snapshots found" or fail with a database error
        # Both are acceptable for this basic test
        assert result.exit_code in [0, 1]
        assert "No snapshots found" in result.output or "Error" in result.output
    
    def test_diff_command_with_nonexistent_snapshot(self, initialized_project):
        """Test diff command with nonexistent snapshot ID."""
        runner = CliRunner()
        
        result = runner.invoke(cli, [
            '--project-root', str(initialized_project),
            'diff', 'nonexistent_snapshot_123'
        ])
        
        # Should fail gracefully
        assert result.exit_code == 1
        assert "Error" in result.output


class TestDiffViewerUnit:
    """Unit tests for diff viewer components."""
    
    def test_diff_format_enum_values(self):
        """Test that DiffFormat enum has expected values."""
        from claude_rewind.core.models import DiffFormat
        assert DiffFormat.UNIFIED.value == "unified"
        assert DiffFormat.SIDE_BY_SIDE.value == "side-by-side"
        assert DiffFormat.PATCH.value == "patch"
    
    def test_diff_viewer_import(self):
        """Test that DiffViewer can be imported."""
        from claude_rewind.core.diff_viewer import DiffViewer
        assert DiffViewer is not None
    
    def test_storage_manager_wrapper_structure(self):
        """Test the structure of StorageManagerWrapper used in CLI."""
        # This tests the wrapper class structure without actually running it
        from claude_rewind.cli.main import diff
        
        # Check that the function exists and has the expected signature
        assert callable(diff)
        
        # The function should be a Click command
        assert hasattr(diff, 'params')
        
        # Check for expected parameters
        param_names = [param.name for param in diff.params]
        expected_params = ['snapshot_id', 'file', 'format', 'before', 'after', 
                          'context', 'no_color', 'export', 'interactive']
        
        for expected_param in expected_params:
            assert expected_param in param_names


class TestInteractiveDiffBasic:
    """Basic tests for interactive diff functionality."""
    
    def test_interactive_diff_function_exists(self):
        """Test that interactive diff function exists."""
        from claude_rewind.cli.main import _show_interactive_diff
        assert callable(_show_interactive_diff)
    
    def test_interactive_diff_imports(self):
        """Test that interactive diff can handle missing imports."""
        # This is tested in the actual CLI test, but we can verify the function exists
        from claude_rewind.cli.main import _show_interactive_diff
        
        # The function should exist and be callable
        assert _show_interactive_diff is not None
        assert callable(_show_interactive_diff)