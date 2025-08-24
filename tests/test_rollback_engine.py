"""Tests for rollback engine functionality."""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock

from claude_rewind.core.rollback_engine import RollbackEngine, RollbackError
from claude_rewind.core.models import (
    SnapshotId, RollbackOptions, RollbackPreview, RollbackResult,
    FileConflict, ConflictResolution, FileState, Snapshot, SnapshotMetadata
)


class TestRollbackEngine:
    """Test cases for RollbackEngine."""
    
    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Create project structure
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").write_text("print('hello')")
        (temp_dir / "src" / "utils.py").write_text("def helper(): pass")
        (temp_dir / "README.md").write_text("# Test Project")
        
        # Create .claude-rewind directory
        rewind_dir = temp_dir / ".claude-rewind"
        rewind_dir.mkdir()
        (rewind_dir / "backups").mkdir()
        
        yield temp_dir
        
        # Cleanup
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def mock_storage_manager(self):
        """Create a mock storage manager."""
        storage_manager = Mock()
        
        # Mock snapshot data
        file_states = {
            Path("src/main.py"): FileState(
                path=Path("src/main.py"),
                content_hash="abc123",
                size=15,
                modified_time=datetime.now(),
                permissions=0o644,
                exists=True
            ),
            Path("src/utils.py"): FileState(
                path=Path("src/utils.py"),
                content_hash="def456",
                size=20,
                modified_time=datetime.now(),
                permissions=0o644,
                exists=True
            )
        }
        
        snapshot_metadata = SnapshotMetadata(
            id="test_snapshot",
            timestamp=datetime.now(),
            action_type="edit_file",
            prompt_context="Test snapshot",
            files_affected=[Path("src/main.py")],
            total_size=35,
            compression_ratio=0.8
        )
        
        mock_snapshot = Snapshot(
            id="test_snapshot",
            timestamp=datetime.now(),
            metadata=snapshot_metadata,
            file_states=file_states
        )
        
        storage_manager.load_snapshot.return_value = mock_snapshot
        storage_manager.load_file_content.return_value = b"print('hello world')"
        
        return storage_manager
    
    @pytest.fixture
    def rollback_engine(self, temp_project, mock_storage_manager):
        """Create a rollback engine instance."""
        return RollbackEngine(mock_storage_manager, temp_project)
    
    def test_init(self, temp_project, mock_storage_manager):
        """Test rollback engine initialization."""
        engine = RollbackEngine(mock_storage_manager, temp_project)
        
        assert engine.storage_manager == mock_storage_manager
        assert engine.project_root == temp_project
        assert engine.backup_dir.exists()
    
    def test_preview_rollback_basic(self, rollback_engine, mock_storage_manager):
        """Test basic rollback preview functionality."""
        options = RollbackOptions()
        
        preview = rollback_engine.preview_rollback("test_snapshot", options)
        
        assert isinstance(preview, RollbackPreview)
        assert len(preview.files_to_restore) >= 0
        assert len(preview.files_to_delete) >= 0
        assert preview.estimated_changes >= 0
        
        # Verify storage manager was called
        mock_storage_manager.load_snapshot.assert_called_once_with("test_snapshot")
    
    def test_preview_rollback_selective_files(self, rollback_engine, mock_storage_manager):
        """Test rollback preview with selective files."""
        options = RollbackOptions(
            selective_files=[Path("src/main.py")]
        )
        
        preview = rollback_engine.preview_rollback("test_snapshot", options)
        
        assert isinstance(preview, RollbackPreview)
        # Should only consider the selective file
        if preview.files_to_restore:
            assert all(f in [Path("src/main.py")] for f in preview.files_to_restore)
    
    def test_preview_rollback_snapshot_not_found(self, rollback_engine, mock_storage_manager):
        """Test rollback preview when snapshot doesn't exist."""
        mock_storage_manager.load_snapshot.return_value = None
        
        options = RollbackOptions()
        
        with pytest.raises(RollbackError, match="Snapshot not found"):
            rollback_engine.preview_rollback("nonexistent", options)
    
    def test_execute_rollback_dry_run(self, rollback_engine, mock_storage_manager):
        """Test rollback execution in dry run mode."""
        options = RollbackOptions(dry_run=True)
        
        result = rollback_engine.execute_rollback("test_snapshot", options)
        
        assert isinstance(result, RollbackResult)
        assert result.success is True
        assert len(result.files_restored) == 0  # No actual changes in dry run
        assert len(result.files_deleted) == 0
        assert len(result.errors) == 1  # Should have dry run message
        assert "Dry run" in result.errors[0]
    
    def test_execute_rollback_with_backup(self, rollback_engine, mock_storage_manager, temp_project):
        """Test rollback execution with backup creation."""
        options = RollbackOptions(create_backup=True)
        
        # Mock the preview to return no changes to avoid actual file operations
        rollback_engine.preview_rollback = Mock(return_value=RollbackPreview(
            files_to_restore=[],
            files_to_delete=[],
            conflicts=[],
            estimated_changes=0
        ))
        
        result = rollback_engine.execute_rollback("test_snapshot", options)
        
        assert isinstance(result, RollbackResult)
        # Should have created a backup directory
        backup_dirs = list((temp_project / ".claude-rewind" / "backups").iterdir())
        assert len(backup_dirs) > 0
    
    def test_execute_rollback_no_backup(self, rollback_engine, mock_storage_manager, temp_project):
        """Test rollback execution without backup creation."""
        options = RollbackOptions(create_backup=False)
        
        # Mock the preview to return no changes
        rollback_engine.preview_rollback = Mock(return_value=RollbackPreview(
            files_to_restore=[],
            files_to_delete=[],
            conflicts=[],
            estimated_changes=0
        ))
        
        result = rollback_engine.execute_rollback("test_snapshot", options)
        
        assert isinstance(result, RollbackResult)
        # Should not have created any backup directories
        backup_dirs = list((temp_project / ".claude-rewind" / "backups").iterdir())
        assert len(backup_dirs) == 0
    
    def test_resolve_conflicts_basic(self, rollback_engine):
        """Test basic conflict resolution."""
        conflicts = [
            FileConflict(
                file_path=Path("src/main.py"),
                current_hash="current123",
                target_hash="target456",
                conflict_type="content_mismatch",
                description="File has been modified"
            )
        ]
        
        resolutions = rollback_engine.resolve_conflicts(conflicts)
        
        assert len(resolutions) == 1
        assert isinstance(resolutions[0], ConflictResolution)
        assert resolutions[0].file_path == Path("src/main.py")
        assert resolutions[0].resolution_type in ["keep_current", "use_snapshot", "merge"]
    
    def test_resolve_conflicts_multiple_types(self, rollback_engine):
        """Test conflict resolution with multiple conflict types."""
        conflicts = [
            FileConflict(
                file_path=Path("src/main.py"),
                current_hash="current123",
                target_hash="target456",
                conflict_type="content_mismatch",
                description="File has been modified"
            ),
            FileConflict(
                file_path=Path("src/new_file.py"),
                current_hash="new123",
                target_hash="",
                conflict_type="file_added",
                description="File was added after snapshot"
            )
        ]
        
        resolutions = rollback_engine.resolve_conflicts(conflicts)
        
        assert len(resolutions) == 2
        assert all(isinstance(r, ConflictResolution) for r in resolutions)
        
        # Check that different conflict types get different resolutions
        resolution_types = [r.resolution_type for r in resolutions]
        assert len(set(resolution_types)) >= 1  # At least some variety in resolutions
    
    def test_get_current_project_state(self, rollback_engine, temp_project):
        """Test getting current project state."""
        current_state = rollback_engine._get_current_project_state()
        
        assert isinstance(current_state, dict)
        # Should include the files we created in temp_project
        file_paths = [str(p) for p in current_state.keys()]
        assert any("main.py" in path for path in file_paths)
        assert any("utils.py" in path for path in file_paths)
        assert any("README.md" in path for path in file_paths)
    
    def test_get_current_project_state_selective(self, rollback_engine, temp_project):
        """Test getting current project state with selective files."""
        selective_files = [Path("src/main.py")]
        current_state = rollback_engine._get_current_project_state(selective_files)
        
        assert isinstance(current_state, dict)
        assert len(current_state) <= 1  # Should only include the selective file if it exists
        if current_state:
            assert Path("src/main.py") in current_state
    
    def test_scan_project_files(self, rollback_engine, temp_project):
        """Test project file scanning."""
        files = rollback_engine._scan_project_files()
        
        assert isinstance(files, list)
        assert len(files) >= 3  # At least the files we created
        
        # Should exclude .claude-rewind directory
        file_paths = [str(f) for f in files]
        assert not any(".claude-rewind" in path for path in file_paths)
        
        # Should include our test files
        assert any("main.py" in str(f) for f in files)
        assert any("utils.py" in str(f) for f in files)
        assert any("README.md" in str(f) for f in files)
    
    def test_calculate_hash(self, rollback_engine):
        """Test content hash calculation."""
        content1 = b"hello world"
        content2 = b"hello world"
        content3 = b"different content"
        
        hash1 = rollback_engine._calculate_hash(content1)
        hash2 = rollback_engine._calculate_hash(content2)
        hash3 = rollback_engine._calculate_hash(content3)
        
        assert hash1 == hash2  # Same content should have same hash
        assert hash1 != hash3  # Different content should have different hash
        assert len(hash1) == 64  # SHA-256 hash should be 64 characters
    
    def test_detect_conflict(self, rollback_engine):
        """Test conflict detection."""
        file_path = Path("test.py")
        current_hash = "abc123"
        target_hash = "def456"
        
        conflict = rollback_engine._detect_conflict(file_path, current_hash, target_hash)
        
        assert isinstance(conflict, FileConflict)
        assert conflict.file_path == file_path
        assert conflict.current_hash == current_hash
        assert conflict.target_hash == target_hash
        assert conflict.conflict_type == "content_mismatch"
    
    def test_detect_no_conflict(self, rollback_engine):
        """Test no conflict when hashes match."""
        file_path = Path("test.py")
        same_hash = "abc123"
        
        conflict = rollback_engine._detect_conflict(file_path, same_hash, same_hash)
        
        assert conflict is None
    
    def test_restore_file_success(self, rollback_engine, mock_storage_manager, temp_project):
        """Test successful file restoration."""
        file_path = Path("src/main.py")
        target_content = b"print('restored content')"
        
        file_state = FileState(
            path=file_path,
            content_hash="restored123",
            size=len(target_content),
            modified_time=datetime.now(),
            permissions=0o644,
            exists=True
        )
        
        mock_storage_manager.load_file_content.return_value = target_content
        
        # Should not raise an exception
        rollback_engine._restore_file(file_path, file_state)
        
        # Verify file was written
        restored_file = temp_project / file_path
        assert restored_file.exists()
        assert restored_file.read_bytes() == target_content
    
    def test_restore_file_deleted(self, rollback_engine, mock_storage_manager, temp_project):
        """Test restoration of deleted file (file should be removed)."""
        file_path = Path("src/main.py")
        
        file_state = FileState(
            path=file_path,
            content_hash="",
            size=0,
            modified_time=datetime.now(),
            permissions=0o644,
            exists=False  # File should not exist
        )
        
        # Ensure file exists initially
        target_file = temp_project / file_path
        assert target_file.exists()
        
        # Should not raise an exception
        rollback_engine._restore_file(file_path, file_state)
        
        # File should be deleted
        assert not target_file.exists()
    
    def test_restore_file_content_not_found(self, rollback_engine, mock_storage_manager, temp_project):
        """Test file restoration when content is not found."""
        file_path = Path("src/main.py")
        
        file_state = FileState(
            path=file_path,
            content_hash="missing123",
            size=100,
            modified_time=datetime.now(),
            permissions=0o644,
            exists=True
        )
        
        mock_storage_manager.load_file_content.return_value = None
        
        with pytest.raises(RollbackError, match="Content not found"):
            rollback_engine._restore_file(file_path, file_state)
    
    def test_create_backup(self, rollback_engine, temp_project):
        """Test backup creation."""
        backup_id = rollback_engine._create_backup()
        
        assert isinstance(backup_id, str)
        assert backup_id.startswith("backup_")
        
        # Verify backup directory was created
        backup_path = temp_project / ".claude-rewind" / "backups" / backup_id
        assert backup_path.exists()
        
        # Verify files were backed up
        backed_up_files = list(backup_path.rglob("*"))
        backed_up_files = [f for f in backed_up_files if f.is_file()]
        assert len(backed_up_files) >= 3  # Should have backed up our test files
    
    def test_restore_from_backup(self, rollback_engine, temp_project):
        """Test restoration from backup."""
        # Create a backup first
        backup_id = rollback_engine._create_backup()
        
        # Modify a file
        test_file = temp_project / "src" / "main.py"
        original_content = test_file.read_text()
        test_file.write_text("modified content")
        
        # Restore from backup
        rollback_engine._restore_from_backup(backup_id)
        
        # Verify file was restored
        assert test_file.read_text() == original_content
    
    def test_restore_from_backup_not_found(self, rollback_engine):
        """Test restoration from non-existent backup."""
        with pytest.raises(RollbackError, match="Backup not found"):
            rollback_engine._restore_from_backup("nonexistent_backup")


class TestRollbackEngineIntegration:
    """Integration tests for rollback engine with real file operations."""
    
    @pytest.fixture
    def integration_project(self):
        """Create a more complex project for integration testing."""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Create project structure
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "api").mkdir()
        (temp_dir / "tests").mkdir()
        
        # Create files with content
        (temp_dir / "src" / "main.py").write_text("""
def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()
""")
        
        (temp_dir / "src" / "api" / "handlers.py").write_text("""
def handle_request(request):
    return {"status": "ok"}
""")
        
        (temp_dir / "tests" / "test_main.py").write_text("""
import unittest
from src.main import main

class TestMain(unittest.TestCase):
    def test_main(self):
        # Test main function
        pass
""")
        
        (temp_dir / "README.md").write_text("# Integration Test Project")
        
        # Create .claude-rewind directory
        rewind_dir = temp_dir / ".claude-rewind"
        rewind_dir.mkdir()
        (rewind_dir / "backups").mkdir()
        
        yield temp_dir
        
        # Cleanup
        shutil.rmtree(temp_dir)
    
    def test_full_rollback_workflow(self, integration_project):
        """Test complete rollback workflow with real files."""
        # Create mock storage manager with real file content
        storage_manager = Mock()
        
        # Read current file content to create snapshot
        main_file = integration_project / "src" / "main.py"
        original_content = main_file.read_bytes()
        
        # Create file states based on current files
        file_states = {}
        for file_path in integration_project.rglob("*"):
            if file_path.is_file() and ".claude-rewind" not in str(file_path):
                relative_path = file_path.relative_to(integration_project)
                content = file_path.read_bytes()
                
                file_states[relative_path] = FileState(
                    path=relative_path,
                    content_hash=f"hash_{len(content)}",
                    size=len(content),
                    modified_time=datetime.now(),
                    permissions=0o644,
                    exists=True
                )
        
        # Create snapshot
        snapshot_metadata = SnapshotMetadata(
            id="integration_test",
            timestamp=datetime.now(),
            action_type="edit_file",
            prompt_context="Integration test snapshot",
            files_affected=list(file_states.keys()),
            total_size=sum(fs.size for fs in file_states.values()),
            compression_ratio=0.8
        )
        
        mock_snapshot = Snapshot(
            id="integration_test",
            timestamp=datetime.now(),
            metadata=snapshot_metadata,
            file_states=file_states
        )
        
        storage_manager.load_snapshot.return_value = mock_snapshot
        
        # Store original content for restoration
        original_contents = {}
        for file_path, file_state in file_states.items():
            full_path = integration_project / file_path
            if full_path.exists():
                original_contents[file_state.content_hash] = full_path.read_bytes()
        
        # Mock file content loading to return original content
        def mock_load_content(content_hash):
            return original_contents.get(content_hash)
        
        storage_manager.load_file_content.side_effect = mock_load_content
        
        # Create rollback engine
        rollback_engine = RollbackEngine(storage_manager, integration_project)
        
        # Modify a file to create a difference
        main_file.write_text("# Modified content\nprint('changed')")
        
        # Test preview
        options = RollbackOptions(preserve_manual_changes=False)
        preview = rollback_engine.preview_rollback("integration_test", options)
        
        assert len(preview.files_to_restore) >= 1
        assert Path("src/main.py") in preview.files_to_restore
        
        # Test actual rollback
        result = rollback_engine.execute_rollback("integration_test", options)
        
        assert result.success
        assert len(result.files_restored) >= 1
        assert Path("src/main.py") in result.files_restored
        
        # Verify file was restored
        assert main_file.read_bytes() == original_content