"""Tests for core data models."""

import pytest
from datetime import datetime
from pathlib import Path
from claude_rewind.core.models import (
    ActionContext, FileState, SnapshotMetadata, ChangeType,
    generate_snapshot_id, generate_session_id
)


class TestModels:
    """Test cases for core data models."""
    
    def test_action_context_creation(self):
        """Test ActionContext creation and attributes."""
        context = ActionContext(
            action_type="edit_file",
            timestamp=datetime.now(),
            prompt_context="Add type hints to function",
            affected_files=[Path("src/api.py")],
            tool_name="str_replace"
        )
        
        assert context.action_type == "edit_file"
        assert isinstance(context.timestamp, datetime)
        assert context.prompt_context == "Add type hints to function"
        assert len(context.affected_files) == 1
        assert context.affected_files[0] == Path("src/api.py")
        assert context.tool_name == "str_replace"
        assert context.session_id is None
    
    def test_file_state_creation(self):
        """Test FileState creation and attributes."""
        file_state = FileState(
            path=Path("src/main.py"),
            content_hash="abc123",
            size=1024,
            modified_time=datetime.now(),
            permissions=644
        )
        
        assert file_state.path == Path("src/main.py")
        assert file_state.content_hash == "abc123"
        assert file_state.size == 1024
        assert isinstance(file_state.modified_time, datetime)
        assert file_state.permissions == 644
        assert file_state.exists is True
    
    def test_snapshot_metadata_creation(self):
        """Test SnapshotMetadata creation and attributes."""
        metadata = SnapshotMetadata(
            id="cr_abc123",
            timestamp=datetime.now(),
            action_type="edit_file",
            prompt_context="Refactor function",
            files_affected=[Path("src/utils.py")],
            total_size=2048,
            compression_ratio=0.75
        )
        
        assert metadata.id == "cr_abc123"
        assert isinstance(metadata.timestamp, datetime)
        assert metadata.action_type == "edit_file"
        assert metadata.prompt_context == "Refactor function"
        assert len(metadata.files_affected) == 1
        assert metadata.total_size == 2048
        assert metadata.compression_ratio == 0.75
        assert metadata.parent_snapshot is None
        assert metadata.bookmark_name is None
    
    def test_change_type_enum(self):
        """Test ChangeType enum values."""
        assert ChangeType.ADDED.value == "added"
        assert ChangeType.MODIFIED.value == "modified"
        assert ChangeType.DELETED.value == "deleted"
    
    def test_id_generation(self):
        """Test ID generation functions."""
        snapshot_id = generate_snapshot_id()
        assert snapshot_id.startswith("cr_")
        assert len(snapshot_id) == 11  # "cr_" + 8 hex chars
        
        session_id = generate_session_id()
        assert session_id.startswith("session_")
        assert len(session_id) == 20  # "session_" + 12 hex chars
        
        # Test uniqueness
        assert generate_snapshot_id() != generate_snapshot_id()
        assert generate_session_id() != generate_session_id()