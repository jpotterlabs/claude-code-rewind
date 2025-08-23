"""Unit tests for SnapshotEngine."""

import os
import tempfile
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from claude_rewind.core.snapshot_engine import SnapshotEngine, SnapshotEngineError
from claude_rewind.core.models import (
    ActionContext, SnapshotId, FileState, ChangeType, TimelineFilters
)


class TestSnapshotEngine:
    """Test cases for SnapshotEngine class."""
    
    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory with test files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "test_project"
            project_root.mkdir()
            
            # Create test files
            (project_root / "main.py").write_text("print('Hello, World!')")
            (project_root / "README.md").write_text("# Test Project")
            
            # Create subdirectory with files
            subdir = project_root / "src"
            subdir.mkdir()
            (subdir / "utils.py").write_text("def helper(): pass")
            
            yield project_root
    
    @pytest.fixture
    def temp_storage(self):
        """Create a temporary storage directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir) / "storage"
    
    @pytest.fixture
    def snapshot_engine(self, temp_project, temp_storage):
        """Create a SnapshotEngine instance for testing."""
        return SnapshotEngine(temp_project, temp_storage)
    
    @pytest.fixture
    def sample_context(self):
        """Create a sample ActionContext for testing."""
        return ActionContext(
            action_type="edit_file",
            timestamp=datetime.now(),
            prompt_context="Add type hints to main function",
            affected_files=[Path("main.py")],
            tool_name="str_replace"
        )
    
    def test_initialization(self, temp_project, temp_storage):
        """Test SnapshotEngine initialization."""
        engine = SnapshotEngine(temp_project, temp_storage)
        
        assert engine.project_root == temp_project.resolve()
        assert engine.storage_root == temp_storage
        assert engine._last_snapshot_id is None
        assert len(engine._last_snapshot_states) == 0
    
    def test_create_snapshot_success(self, snapshot_engine, sample_context):
        """Test successful snapshot creation."""
        snapshot_id = snapshot_engine.create_snapshot(sample_context)
        
        # Verify snapshot ID format
        assert snapshot_id.startswith("cr_")
        assert len(snapshot_id) == 11  # "cr_" + 8 hex chars
        
        # Verify snapshot can be retrieved
        snapshot = snapshot_engine.get_snapshot(snapshot_id)
        assert snapshot is not None
        assert snapshot.id == snapshot_id
        assert snapshot.metadata.action_type == "edit_file"
        assert snapshot.metadata.prompt_context == "Add type hints to main function"
        
        # Verify file states are captured
        assert len(snapshot.file_states) >= 3  # main.py, README.md, src/utils.py
        assert Path("main.py") in snapshot.file_states
        assert Path("README.md") in snapshot.file_states
        assert Path("src/utils.py") in snapshot.file_states
    
    def test_create_snapshot_incremental(self, snapshot_engine, sample_context, temp_project):
        """Test incremental snapshot creation."""
        # Create first snapshot
        snapshot_id1 = snapshot_engine.create_snapshot(sample_context)
        
        # Modify a file
        (temp_project / "main.py").write_text("print('Hello, Updated World!')")
        
        # Create second snapshot
        context2 = ActionContext(
            action_type="edit_file",
            timestamp=datetime.now(),
            prompt_context="Update greeting message",
            affected_files=[Path("main.py")],
            tool_name="str_replace"
        )
        snapshot_id2 = snapshot_engine.create_snapshot(context2)
        
        # Verify incremental relationship
        snapshot2 = snapshot_engine.get_snapshot(snapshot_id2)
        assert snapshot2.metadata.parent_snapshot == snapshot_id1
        
        # Verify cache is updated
        assert snapshot_engine._last_snapshot_id == snapshot_id2
        assert len(snapshot_engine._last_snapshot_states) >= 3
    
    def test_file_change_detection(self, snapshot_engine, sample_context, temp_project):
        """Test file change detection between snapshots."""
        # Create initial snapshot
        snapshot_engine.create_snapshot(sample_context)
        
        # Add a new file
        (temp_project / "new_file.py").write_text("# New file")
        
        # Modify existing file
        (temp_project / "main.py").write_text("print('Modified!')")
        
        # Delete a file
        (temp_project / "README.md").unlink()
        
        # Create second snapshot
        context2 = ActionContext(
            action_type="refactor",
            timestamp=datetime.now(),
            prompt_context="Refactor project structure",
            affected_files=[Path("main.py"), Path("new_file.py")],
            tool_name="multiple_edits"
        )
        snapshot_id2 = snapshot_engine.create_snapshot(context2)
        
        # Verify changes are detected
        snapshot2 = snapshot_engine.get_snapshot(snapshot_id2)
        assert snapshot2 is not None
        
        # Check that new file is included
        assert Path("new_file.py") in snapshot2.file_states
        
        # Check that deleted file is marked as not existing
        if Path("README.md") in snapshot2.file_states:
            assert not snapshot2.file_states[Path("README.md")].exists
    
    def test_list_snapshots(self, snapshot_engine, sample_context):
        """Test listing snapshots."""
        # Initially no snapshots
        snapshots = snapshot_engine.list_snapshots()
        assert len(snapshots) == 0
        
        # Create multiple snapshots
        snapshot_id1 = snapshot_engine.create_snapshot(sample_context)
        
        context2 = ActionContext(
            action_type="create_file",
            timestamp=datetime.now(),
            prompt_context="Add new utility",
            affected_files=[Path("utils.py")],
            tool_name="str_replace"
        )
        snapshot_id2 = snapshot_engine.create_snapshot(context2)
        
        # List all snapshots
        snapshots = snapshot_engine.list_snapshots()
        assert len(snapshots) == 2
        
        # Verify order (newest first)
        assert snapshots[0].id == snapshot_id2
        assert snapshots[1].id == snapshot_id1
    
    def test_list_snapshots_with_filters(self, snapshot_engine, sample_context):
        """Test listing snapshots with filters."""
        # Create snapshots with different action types
        snapshot_id1 = snapshot_engine.create_snapshot(sample_context)
        
        context2 = ActionContext(
            action_type="create_file",
            timestamp=datetime.now(),
            prompt_context="Add new file",
            affected_files=[Path("new.py")],
            tool_name="str_replace"
        )
        snapshot_id2 = snapshot_engine.create_snapshot(context2)
        
        # Filter by action type
        filters = TimelineFilters(action_types=["edit_file"])
        filtered_snapshots = snapshot_engine.list_snapshots(filters)
        
        assert len(filtered_snapshots) == 1
        assert filtered_snapshots[0].id == snapshot_id1
    
    def test_get_snapshot_not_found(self, snapshot_engine):
        """Test getting non-existent snapshot."""
        snapshot = snapshot_engine.get_snapshot("nonexistent_id")
        assert snapshot is None
    
    def test_delete_snapshot(self, snapshot_engine, sample_context):
        """Test snapshot deletion."""
        # Create snapshot
        snapshot_id = snapshot_engine.create_snapshot(sample_context)
        
        # Verify it exists
        assert snapshot_engine.get_snapshot(snapshot_id) is not None
        
        # Delete snapshot
        success = snapshot_engine.delete_snapshot(snapshot_id)
        assert success is True
        
        # Verify it's gone
        assert snapshot_engine.get_snapshot(snapshot_id) is None
        
        # Verify cache is cleared if it was the last snapshot
        if snapshot_engine._last_snapshot_id == snapshot_id:
            assert snapshot_engine._last_snapshot_id is None
            assert len(snapshot_engine._last_snapshot_states) == 0
    
    def test_delete_nonexistent_snapshot(self, snapshot_engine):
        """Test deleting non-existent snapshot."""
        success = snapshot_engine.delete_snapshot("nonexistent_id")
        assert success is False
    
    def test_file_hash_calculation(self, snapshot_engine, temp_project):
        """Test file hash calculation."""
        test_file = temp_project / "test_hash.txt"
        test_content = "Hello, World!"
        test_file.write_text(test_content)
        
        hash1 = snapshot_engine._calculate_file_hash(test_file)
        hash2 = snapshot_engine._calculate_file_hash(test_file)
        
        # Same content should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length
        
        # Different content should produce different hash
        test_file.write_text("Different content")
        hash3 = snapshot_engine._calculate_file_hash(test_file)
        assert hash1 != hash3
    
    def test_should_ignore_directory(self, snapshot_engine, temp_project):
        """Test directory ignore logic."""
        # Test common ignore patterns
        assert snapshot_engine._should_ignore_directory(temp_project / ".git")
        assert snapshot_engine._should_ignore_directory(temp_project / "__pycache__")
        assert snapshot_engine._should_ignore_directory(temp_project / "node_modules")
        assert snapshot_engine._should_ignore_directory(temp_project / ".vscode")
        assert snapshot_engine._should_ignore_directory(temp_project / ".claude-rewind")
        
        # Test normal directories are not ignored
        assert not snapshot_engine._should_ignore_directory(temp_project / "src")
        assert not snapshot_engine._should_ignore_directory(temp_project / "tests")
    
    def test_should_ignore_file(self, snapshot_engine, temp_project):
        """Test file ignore logic."""
        # Test common ignore patterns
        assert snapshot_engine._should_ignore_file(temp_project / ".DS_Store")
        assert snapshot_engine._should_ignore_file(temp_project / "Thumbs.db")
        assert snapshot_engine._should_ignore_file(temp_project / "test.pyc")
        assert snapshot_engine._should_ignore_file(temp_project / "debug.log")
        assert snapshot_engine._should_ignore_file(temp_project / "temp.tmp")
        
        # Test normal files are not ignored
        assert not snapshot_engine._should_ignore_file(temp_project / "main.py")
        assert not snapshot_engine._should_ignore_file(temp_project / "README.md")
        assert not snapshot_engine._should_ignore_file(temp_project / "config.json")
    
    def test_scan_project_state(self, snapshot_engine, temp_project):
        """Test project state scanning."""
        # Add some files to ignore
        (temp_project / ".DS_Store").write_text("ignore me")
        (temp_project / "__pycache__").mkdir()
        (temp_project / "__pycache__" / "test.pyc").write_text("compiled")
        
        file_states = snapshot_engine._scan_project_state()
        
        # Should include normal files
        assert any(state.path.name == "main.py" for state in file_states.values())
        assert any(state.path.name == "README.md" for state in file_states.values())
        assert any(state.path.name == "utils.py" for state in file_states.values())
        
        # Should exclude ignored files
        assert not any(state.path.name == ".DS_Store" for state in file_states.values())
        assert not any(state.path.name == "test.pyc" for state in file_states.values())
        
        # Verify file state properties
        for state in file_states.values():
            assert state.exists is True
            assert state.size >= 0
            assert len(state.content_hash) == 64  # SHA-256
            assert state.modified_time is not None
            assert state.permissions > 0
    
    def test_matches_pattern(self, snapshot_engine):
        """Test pattern matching for file filters."""
        # Test exact matches
        assert snapshot_engine._matches_pattern(Path("main.py"), ["main.py"])
        assert snapshot_engine._matches_pattern(Path("src/utils.py"), ["utils.py"])
        
        # Test wildcard patterns
        assert snapshot_engine._matches_pattern(Path("test.py"), ["*.py"])
        assert snapshot_engine._matches_pattern(Path("src/main.py"), ["src/*.py"])
        
        # Test substring matches
        assert snapshot_engine._matches_pattern(Path("test_file.py"), ["test"])
        
        # Test no matches
        assert not snapshot_engine._matches_pattern(Path("main.py"), ["*.js"])
        assert not snapshot_engine._matches_pattern(Path("src/utils.py"), ["test"])
    
    def test_get_incremental_stats(self, snapshot_engine, sample_context):
        """Test incremental statistics."""
        # Initially no incremental data
        stats = snapshot_engine.get_incremental_stats()
        assert stats['cached_files'] == 0
        assert stats['last_snapshot_id'] == 'none'
        assert stats['incremental_enabled'] is False
        
        # After creating snapshot
        snapshot_id = snapshot_engine.create_snapshot(sample_context)
        stats = snapshot_engine.get_incremental_stats()
        
        assert stats['cached_files'] > 0
        assert stats['last_snapshot_id'] == snapshot_id
        assert stats['incremental_enabled'] is True
    
    def test_create_snapshot_error_handling(self, snapshot_engine, sample_context):
        """Test error handling during snapshot creation."""
        # Mock database manager to raise an exception
        with patch.object(snapshot_engine.db_manager, 'create_snapshot', 
                         side_effect=Exception("Database error")):
            
            with pytest.raises(SnapshotEngineError):
                snapshot_engine.create_snapshot(sample_context)
    
    def test_create_snapshot_cleanup_on_failure(self, snapshot_engine, sample_context):
        """Test cleanup when snapshot creation fails."""
        # Mock file store to raise an exception after partial creation
        original_create = snapshot_engine.file_store.create_snapshot
        
        def failing_create(*args, **kwargs):
            # Create partial state then fail
            result = original_create(*args, **kwargs)
            raise Exception("Storage error")
        
        with patch.object(snapshot_engine.file_store, 'create_snapshot', 
                         side_effect=failing_create):
            
            with pytest.raises(SnapshotEngineError):
                snapshot_engine.create_snapshot(sample_context)
            
            # Verify cleanup was attempted (no partial snapshots left)
            snapshots = snapshot_engine.list_snapshots()
            assert len(snapshots) == 0
    
    def test_file_hash_error_handling(self, snapshot_engine, temp_project):
        """Test file hash calculation with unreadable files."""
        # Create a file and then make it unreadable
        test_file = temp_project / "unreadable.txt"
        test_file.write_text("test content")
        
        # Mock open to raise permission error
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            hash_result = snapshot_engine._calculate_file_hash(test_file)
            
            # Should return error hash instead of crashing
            assert hash_result.startswith("error_")
    
    def test_concurrent_snapshot_creation(self, snapshot_engine, sample_context):
        """Test that concurrent snapshot creation doesn't cause issues."""
        # This is a basic test - in a real scenario you'd use threading
        snapshot_id1 = snapshot_engine.create_snapshot(sample_context)
        snapshot_id2 = snapshot_engine.create_snapshot(sample_context)
        
        # Should create different snapshots
        assert snapshot_id1 != snapshot_id2
        
        # Both should be retrievable
        assert snapshot_engine.get_snapshot(snapshot_id1) is not None
        assert snapshot_engine.get_snapshot(snapshot_id2) is not None
    
    def test_large_file_handling(self, snapshot_engine, sample_context, temp_project):
        """Test handling of larger files."""
        # Create a larger test file (1MB)
        large_content = "x" * (1024 * 1024)  # 1MB of 'x' characters
        large_file = temp_project / "large_file.txt"
        large_file.write_text(large_content)
        
        # Should handle large file without issues
        snapshot_id = snapshot_engine.create_snapshot(sample_context)
        snapshot = snapshot_engine.get_snapshot(snapshot_id)
        
        assert snapshot is not None
        assert Path("large_file.txt") in snapshot.file_states
        assert snapshot.file_states[Path("large_file.txt")].size == len(large_content)
    
    def test_empty_project_snapshot(self, temp_storage):
        """Test creating snapshot of empty project."""
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_project = Path(temp_dir) / "empty"
            empty_project.mkdir()
            
            engine = SnapshotEngine(empty_project, temp_storage)
            context = ActionContext(
                action_type="init",
                timestamp=datetime.now(),
                prompt_context="Initialize empty project",
                affected_files=[],
                tool_name="init"
            )
            
            snapshot_id = engine.create_snapshot(context)
            snapshot = engine.get_snapshot(snapshot_id)
            
            assert snapshot is not None
            assert len(snapshot.file_states) == 0
            assert snapshot.metadata.total_size == 0