"""Unit tests for diff viewer functionality."""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from claude_rewind.core.diff_viewer import DiffViewer, DiffViewerError
from claude_rewind.core.models import (
    SnapshotId, DiffFormat, Snapshot, SnapshotMetadata, FileState,
    ChangeType, FileChange, LineChange
)


class TestDiffViewer:
    """Test cases for DiffViewer class."""
    
    @pytest.fixture
    def mock_storage_manager(self):
        """Create mock storage manager."""
        return Mock()
    
    @pytest.fixture
    def diff_viewer(self, mock_storage_manager):
        """Create DiffViewer instance with mock storage."""
        return DiffViewer(
            storage_manager=mock_storage_manager,
            context_lines=3,
            enable_colors=False  # Disable colors for easier testing
        )
    
    @pytest.fixture
    def sample_snapshot(self):
        """Create sample snapshot for testing."""
        metadata = SnapshotMetadata(
            id="test_snapshot",
            timestamp=datetime.now(),
            action_type="edit_file",
            prompt_context="Test edit",
            files_affected=[Path("test.py")],
            total_size=100,
            compression_ratio=0.5
        )
        
        file_state = FileState(
            path=Path("test.py"),
            content_hash="abc123",
            size=50,
            modified_time=datetime.now(),
            permissions=0o644,
            exists=True
        )
        
        return Snapshot(
            id="test_snapshot",
            timestamp=datetime.now(),
            metadata=metadata,
            file_states={Path("test.py"): file_state}
        )
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for file operations."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_init_with_defaults(self, mock_storage_manager):
        """Test DiffViewer initialization with default parameters."""
        viewer = DiffViewer(mock_storage_manager)
        
        assert viewer.storage_manager == mock_storage_manager
        assert viewer.context_lines == 3
        assert viewer.enable_colors is True
    
    def test_init_with_custom_params(self, mock_storage_manager):
        """Test DiffViewer initialization with custom parameters."""
        viewer = DiffViewer(
            storage_manager=mock_storage_manager,
            context_lines=5,
            enable_colors=False
        )
        
        assert viewer.context_lines == 5
        assert viewer.enable_colors is False
    
    @patch('claude_rewind.core.diff_viewer.PYGMENTS_AVAILABLE', False)
    def test_init_without_pygments(self, mock_storage_manager):
        """Test initialization when Pygments is not available."""
        viewer = DiffViewer(mock_storage_manager, enable_colors=True)
        assert viewer.syntax_highlighting is False
    
    def test_get_file_content_success(self, diff_viewer, mock_storage_manager, sample_snapshot):
        """Test successful file content retrieval."""
        # Setup mock
        mock_storage_manager.load_snapshot.return_value = sample_snapshot
        mock_storage_manager.load_file_content.return_value = b"print('hello world')\n"
        
        # Test
        content = diff_viewer._get_file_content("test_snapshot", Path("test.py"))
        
        assert content == "print('hello world')\n"
        mock_storage_manager.load_snapshot.assert_called_once_with("test_snapshot")
        mock_storage_manager.load_file_content.assert_called_once_with("abc123")
    
    def test_get_file_content_binary_file(self, diff_viewer, mock_storage_manager, sample_snapshot):
        """Test file content retrieval for binary files."""
        # Setup mock with binary content
        mock_storage_manager.load_snapshot.return_value = sample_snapshot
        mock_storage_manager.load_file_content.return_value = b'\x89PNG\r\n\x1a\n'
        
        # Test
        content = diff_viewer._get_file_content("test_snapshot", Path("test.py"))
        
        assert content == "<Binary file: 8 bytes>"
    
    def test_get_file_content_file_not_in_snapshot(self, diff_viewer, mock_storage_manager, sample_snapshot):
        """Test file content retrieval when file is not in snapshot."""
        mock_storage_manager.load_snapshot.return_value = sample_snapshot
        
        content = diff_viewer._get_file_content("test_snapshot", Path("nonexistent.py"))
        
        assert content is None
    
    def test_get_file_content_file_deleted(self, diff_viewer, mock_storage_manager):
        """Test file content retrieval for deleted files."""
        # Create snapshot with deleted file
        metadata = SnapshotMetadata(
            id="test_snapshot",
            timestamp=datetime.now(),
            action_type="delete_file",
            prompt_context="Test delete",
            files_affected=[Path("deleted.py")],
            total_size=0,
            compression_ratio=0.0
        )
        
        file_state = FileState(
            path=Path("deleted.py"),
            content_hash="",
            size=0,
            modified_time=datetime.now(),
            permissions=0o644,
            exists=False
        )
        
        snapshot = Snapshot(
            id="test_snapshot",
            timestamp=datetime.now(),
            metadata=metadata,
            file_states={Path("deleted.py"): file_state}
        )
        
        mock_storage_manager.load_snapshot.return_value = snapshot
        
        content = diff_viewer._get_file_content("test_snapshot", Path("deleted.py"))
        
        assert content is None
    
    def test_get_file_content_snapshot_not_found(self, diff_viewer, mock_storage_manager):
        """Test file content retrieval when snapshot is not found."""
        mock_storage_manager.load_snapshot.return_value = None
        
        with pytest.raises(DiffViewerError, match="Snapshot not found"):
            diff_viewer._get_file_content("nonexistent", Path("test.py"))
    
    def test_get_current_file_content_success(self, diff_viewer, temp_dir):
        """Test successful current file content retrieval."""
        # Create test file
        test_file = temp_dir / "test.py"
        test_file.write_text("print('current content')\n")
        
        content = diff_viewer._get_current_file_content(test_file)
        
        assert content == "print('current content')\n"
    
    def test_get_current_file_content_nonexistent(self, diff_viewer, temp_dir):
        """Test current file content retrieval for nonexistent file."""
        nonexistent_file = temp_dir / "nonexistent.py"
        
        content = diff_viewer._get_current_file_content(nonexistent_file)
        
        assert content is None
    
    def test_get_current_file_content_binary(self, diff_viewer, temp_dir):
        """Test current file content retrieval for binary files."""
        # Create binary file
        binary_file = temp_dir / "image.png"
        binary_file.write_bytes(b'\x89PNG\r\n\x1a\n')
        
        content = diff_viewer._get_current_file_content(binary_file)
        
        assert content == "<Binary file: 8 bytes>"
    
    def test_generate_unified_diff_basic(self, diff_viewer):
        """Test basic unified diff generation."""
        before_content = "line1\nline2\nline3\n"
        after_content = "line1\nmodified line2\nline3\n"
        
        diff = diff_viewer._generate_unified_diff(
            before_content, after_content,
            "before.py", "after.py", Path("test.py")
        )
        
        assert "--- before.py" in diff
        assert "+++ after.py" in diff
        assert "-line2" in diff
        assert "+modified line2" in diff
    
    def test_generate_unified_diff_file_creation(self, diff_viewer):
        """Test unified diff for file creation."""
        before_content = None
        after_content = "new file content\n"
        
        diff = diff_viewer._generate_unified_diff(
            before_content, after_content,
            "/dev/null", "new.py", Path("new.py")
        )
        
        assert "--- /dev/null" in diff
        assert "+++ new.py" in diff
        assert "+new file content" in diff
    
    def test_generate_unified_diff_file_deletion(self, diff_viewer):
        """Test unified diff for file deletion."""
        before_content = "deleted file content\n"
        after_content = None
        
        diff = diff_viewer._generate_unified_diff(
            before_content, after_content,
            "deleted.py", "/dev/null", Path("deleted.py")
        )
        
        assert "--- deleted.py" in diff
        assert "+++ /dev/null" in diff
        assert "-deleted file content" in diff
    
    def test_generate_unified_diff_no_changes(self, diff_viewer):
        """Test unified diff when there are no changes."""
        content = "same content\n"
        
        diff = diff_viewer._generate_unified_diff(
            content, content,
            "before.py", "after.py", Path("test.py")
        )
        
        assert diff == ""
    
    def test_generate_side_by_side_diff_basic(self, diff_viewer):
        """Test basic side-by-side diff generation."""
        before_content = "line1\nline2\nline3"
        after_content = "line1\nmodified line2\nline3"
        
        diff = diff_viewer._generate_side_by_side_diff(
            before_content, after_content,
            "before.py", "after.py", Path("test.py"), width=80
        )
        
        assert "before.py" in diff
        assert "after.py" in diff
        assert "line2" in diff
        assert "modified line2" in diff
        assert "|" in diff  # Column separator
    
    def test_generate_patch_format(self, diff_viewer):
        """Test patch format generation."""
        before_content = "line1\nline2\nline3\n"
        after_content = "line1\nmodified line2\nline3\n"
        
        patch = diff_viewer._generate_patch_format(
            before_content, after_content,
            "before", "after", Path("test.py")
        )
        
        assert "--- a/test.py" in patch
        assert "+++ b/test.py" in patch
        assert "-line2" in patch
        assert "+modified line2" in patch
    
    def test_show_snapshot_diff_success(self, diff_viewer, mock_storage_manager, sample_snapshot, temp_dir):
        """Test successful snapshot diff generation."""
        # Setup mock
        mock_storage_manager.load_snapshot.return_value = sample_snapshot
        mock_storage_manager.load_file_content.return_value = b"original content\n"
        
        # Create current file with different content
        current_file = temp_dir / "test.py"
        current_file.write_text("modified content\n")
        
        # Mock Path.cwd() to return temp_dir
        with patch('pathlib.Path.cwd', return_value=temp_dir):
            diff = diff_viewer.show_snapshot_diff("test_snapshot")
        
        assert "Diff for snapshot test_snapshot" in diff
        assert "test.py" in diff
        assert "original content" in diff or "modified content" in diff
    
    def test_show_snapshot_diff_no_changes(self, diff_viewer, mock_storage_manager, sample_snapshot, temp_dir):
        """Test snapshot diff when there are no changes."""
        # Setup mock with same content
        mock_storage_manager.load_snapshot.return_value = sample_snapshot
        mock_storage_manager.load_file_content.return_value = b"same content\n"
        
        # Mock directory scanning to only return the test file
        def mock_rglob(pattern):
            if pattern == '*':
                return [temp_dir / "test.py"]
            return []
        
        # Mock _get_current_file_content to return the same content
        with patch('pathlib.Path.cwd', return_value=temp_dir), \
             patch.object(Path, 'rglob', mock_rglob), \
             patch.object(diff_viewer, '_get_current_file_content', return_value="same content\n"):
            diff = diff_viewer.show_snapshot_diff("test_snapshot")
        
        assert "No differences found" in diff
    
    def test_show_snapshot_diff_snapshot_not_found(self, diff_viewer, mock_storage_manager):
        """Test snapshot diff when snapshot is not found."""
        mock_storage_manager.load_snapshot.return_value = None
        
        with pytest.raises(DiffViewerError, match="Snapshot not found"):
            diff_viewer.show_snapshot_diff("nonexistent")
    
    def test_show_file_diff_success(self, diff_viewer, mock_storage_manager):
        """Test successful file diff between snapshots."""
        # Setup mocks for two different contents
        def mock_get_file_content(snapshot_id, file_path):
            if snapshot_id == "snapshot1":
                return "original content\n"
            elif snapshot_id == "snapshot2":
                return "modified content\n"
            return None
        
        with patch.object(diff_viewer, '_get_file_content', side_effect=mock_get_file_content):
            diff = diff_viewer.show_file_diff(
                Path("test.py"), "snapshot1", "snapshot2"
            )
        
        assert "Diff for test.py between snapshots" in diff
        assert "original content" in diff
        assert "modified content" in diff
    
    def test_show_file_diff_no_changes(self, diff_viewer, mock_storage_manager):
        """Test file diff when there are no changes."""
        with patch.object(diff_viewer, '_get_file_content', return_value="same content\n"):
            diff = diff_viewer.show_file_diff(
                Path("test.py"), "snapshot1", "snapshot2"
            )
        
        assert "No differences found" in diff
    
    def test_export_diff_disables_colors(self, diff_viewer, mock_storage_manager, sample_snapshot):
        """Test that export_diff disables colors temporarily."""
        mock_storage_manager.load_snapshot.return_value = sample_snapshot
        
        # Enable colors initially
        diff_viewer.enable_colors = True
        
        with patch.object(diff_viewer, 'show_snapshot_diff', return_value="test diff") as mock_show:
            result = diff_viewer.export_diff("test_snapshot", DiffFormat.PATCH)
        
        # Colors should be restored after export
        assert diff_viewer.enable_colors is True
        assert result == "test diff"
        mock_show.assert_called_once_with("test_snapshot", DiffFormat.PATCH)
    
    def test_get_file_changes_success(self, diff_viewer, mock_storage_manager, sample_snapshot, temp_dir):
        """Test successful file changes retrieval."""
        # Setup mock
        mock_storage_manager.load_snapshot.return_value = sample_snapshot
        mock_storage_manager.load_file_content.return_value = b"original line1\noriginal line2\n"
        
        # Mock directory scanning to only return the test file
        def mock_rglob(pattern):
            if pattern == '*':
                return [temp_dir / "test.py"]
            return []
        
        # Mock _get_current_file_content to return the modified content
        def mock_get_current_content(file_path):
            if file_path == Path("test.py"):
                return "modified line1\noriginal line2\n"
            return None
        
        with patch('pathlib.Path.cwd', return_value=temp_dir), \
             patch.object(Path, 'rglob', mock_rglob), \
             patch.object(diff_viewer, '_get_current_file_content', side_effect=mock_get_current_content):
            file_changes = diff_viewer.get_file_changes("test_snapshot")
        
        assert len(file_changes) == 1
        change = file_changes[0]
        assert change.path == Path("test.py")
        assert change.change_type == ChangeType.MODIFIED
        assert len(change.line_changes) > 0
    
    def test_get_file_changes_file_added(self, diff_viewer, mock_storage_manager, temp_dir):
        """Test file changes for newly added file."""
        # Create snapshot without the file
        metadata = SnapshotMetadata(
            id="test_snapshot",
            timestamp=datetime.now(),
            action_type="create_file",
            prompt_context="Test create",
            files_affected=[],
            total_size=0,
            compression_ratio=0.0
        )
        
        snapshot = Snapshot(
            id="test_snapshot",
            timestamp=datetime.now(),
            metadata=metadata,
            file_states={}
        )
        
        mock_storage_manager.load_snapshot.return_value = snapshot
        
        # Create a mock Path object for the current working directory
        mock_cwd = Mock()
        
        # Mock current directory scanning to include the new file
        def mock_rglob(pattern):
            if pattern == '*':
                # Return a mock file object that behaves like a Path
                mock_file = Mock()
                mock_file.is_file.return_value = True
                mock_file.relative_to.return_value = Path("new.py")
                return [mock_file]
            return []
        
        mock_cwd.rglob = mock_rglob
        
        # Mock _get_current_file_content to return content for new file
        def mock_get_current_content(file_path):
            if file_path == Path("new.py"):
                return "new file content\n"
            return None
        
        with patch('pathlib.Path.cwd', return_value=mock_cwd), \
             patch.object(diff_viewer, '_get_current_file_content', side_effect=mock_get_current_content):
            file_changes = diff_viewer.get_file_changes("test_snapshot")
        
        assert len(file_changes) == 1
        change = file_changes[0]
        assert change.path == Path("new.py")
        assert change.change_type == ChangeType.ADDED
    
    def test_get_file_changes_file_deleted(self, diff_viewer, mock_storage_manager, sample_snapshot, temp_dir):
        """Test file changes for deleted file."""
        # Setup mock with file in snapshot
        mock_storage_manager.load_snapshot.return_value = sample_snapshot
        mock_storage_manager.load_file_content.return_value = b"deleted content\n"
        
        # Don't create the current file (simulating deletion)
        with patch('pathlib.Path.cwd', return_value=temp_dir):
            file_changes = diff_viewer.get_file_changes("test_snapshot")
        
        assert len(file_changes) == 1
        change = file_changes[0]
        assert change.path == Path("test.py")
        assert change.change_type == ChangeType.DELETED
    
    def test_different_diff_formats(self, diff_viewer):
        """Test all supported diff formats."""
        before_content = "line1\nline2\nline3\n"
        after_content = "line1\nmodified line2\nline3\n"
        file_path = Path("test.py")
        
        # Test unified format
        unified_diff = diff_viewer._generate_unified_diff(
            before_content, after_content, "before", "after", file_path
        )
        assert "@@" in unified_diff  # Hunk header
        
        # Test side-by-side format
        side_by_side_diff = diff_viewer._generate_side_by_side_diff(
            before_content, after_content, "before", "after", file_path
        )
        assert "|" in side_by_side_diff  # Column separator
        
        # Test patch format
        patch_diff = diff_viewer._generate_patch_format(
            before_content, after_content, "before", "after", file_path
        )
        assert "--- a/test.py" in patch_diff
        assert "+++ b/test.py" in patch_diff
    
    @patch('claude_rewind.core.diff_viewer.PYGMENTS_AVAILABLE', True)
    def test_syntax_highlighting_enabled(self, mock_storage_manager):
        """Test that syntax highlighting is enabled when Pygments is available."""
        with patch('claude_rewind.core.diff_viewer.Terminal256Formatter'):
            viewer = DiffViewer(mock_storage_manager, enable_colors=True)
            assert viewer.syntax_highlighting is True
    
    def test_error_handling_in_get_file_content(self, diff_viewer, mock_storage_manager):
        """Test error handling in _get_file_content method."""
        mock_storage_manager.load_snapshot.side_effect = Exception("Storage error")
        
        with pytest.raises(DiffViewerError, match="Failed to get file content"):
            diff_viewer._get_file_content("test_snapshot", Path("test.py"))
    
    def test_context_lines_configuration(self, mock_storage_manager):
        """Test that context lines configuration is respected."""
        viewer = DiffViewer(mock_storage_manager, context_lines=5, enable_colors=False)
        
        before_content = "\n".join([f"line{i}" for i in range(1, 11)])
        after_content = "\n".join([f"line{i}" if i != 5 else "modified line5" for i in range(1, 11)])
        
        diff = viewer._generate_unified_diff(
            before_content, after_content,
            "before", "after", Path("test.py")
        )
        
        # Check that the diff contains the expected context
        assert "line2" in diff  # Context before change
        assert "line3" in diff  # Context before change
        assert "line4" in diff  # Context before change
        assert "line6" in diff  # Context after change
        assert "line7" in diff  # Context after change
        assert "line8" in diff  # Context after change
        assert "-line5" in diff  # Removed line
        assert "+modified line5" in diff  # Added line


class TestDiffViewerIntegration:
    """Integration tests for DiffViewer with real file operations."""
    
    @pytest.fixture
    def temp_project(self):
        """Create temporary project directory."""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Create sample files
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").write_text(
            "def main():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    main()\n"
        )
        (temp_dir / "README.md").write_text("# Test Project\n\nThis is a test project.\n")
        
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_real_file_diff_generation(self, temp_project):
        """Test diff generation with real files."""
        # Create mock storage manager
        mock_storage = Mock()
        
        # Create DiffViewer
        viewer = DiffViewer(mock_storage, enable_colors=False)
        
        # Test current file content reading
        main_file = temp_project / "src" / "main.py"
        content = viewer._get_current_file_content(main_file)
        
        assert "def main():" in content
        assert "print('Hello, World!')" in content
        
        # Test unified diff generation
        original_content = "def main():\n    print('Hello!')\n"
        current_content = content
        
        diff = viewer._generate_unified_diff(
            original_content, current_content,
            "original", "current", main_file
        )
        
        assert "def main():" in diff
        assert "Hello!" in diff or "Hello, World!" in diff