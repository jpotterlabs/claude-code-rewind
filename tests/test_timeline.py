"""Tests for timeline management functionality."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

from claude_rewind.core.timeline import TimelineManager
from claude_rewind.core.models import (
    SnapshotMetadata, TimelineFilters, SnapshotId, generate_snapshot_id
)
from claude_rewind.storage.database import DatabaseManager


class TestTimelineManager:
    """Test cases for TimelineManager class."""
    
    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock database manager."""
        return Mock(spec=DatabaseManager)
    
    @pytest.fixture
    def mock_console(self):
        """Create a mock Rich console."""
        console = Mock()
        console.print = Mock()
        console.clear = Mock()
        return console
    
    @pytest.fixture
    def sample_snapshots(self):
        """Create sample snapshot metadata for testing."""
        now = datetime.now()
        
        return [
            SnapshotMetadata(
                id=generate_snapshot_id(),
                timestamp=now - timedelta(hours=2),
                action_type="edit_file",
                prompt_context="Add type hints to API functions",
                files_affected=[Path("src/api.py"), Path("src/utils.py")],
                total_size=1024,
                compression_ratio=0.7
            ),
            SnapshotMetadata(
                id=generate_snapshot_id(),
                timestamp=now - timedelta(hours=1),
                action_type="create_file",
                prompt_context="Create new test file for API endpoints",
                files_affected=[Path("tests/test_api.py")],
                total_size=512,
                compression_ratio=0.8
            ),
            SnapshotMetadata(
                id=generate_snapshot_id(),
                timestamp=now,
                action_type="refactor",
                prompt_context="Extract utility functions to separate module",
                files_affected=[Path("src/api.py"), Path("src/utils.py"), Path("src/helpers.py")],
                total_size=2048,
                compression_ratio=0.6
            )
        ]
    
    @pytest.fixture
    def timeline_manager(self, mock_db_manager, mock_console):
        """Create TimelineManager instance with mocked dependencies."""
        return TimelineManager(mock_db_manager, mock_console)
    
    def test_init(self, mock_db_manager, mock_console):
        """Test TimelineManager initialization."""
        manager = TimelineManager(mock_db_manager, mock_console)
        
        assert manager.db_manager == mock_db_manager
        assert manager.console == mock_console
        assert isinstance(manager._bookmarks, dict)
    
    def test_init_without_console(self, mock_db_manager):
        """Test TimelineManager initialization without console."""
        manager = TimelineManager(mock_db_manager)
        
        assert manager.db_manager == mock_db_manager
        assert manager.console is not None  # Should create default console
    
    def test_filter_snapshots_no_filters(self, timeline_manager, sample_snapshots):
        """Test filtering snapshots with no filters applied."""
        timeline_manager.db_manager.list_snapshots.return_value = sample_snapshots
        
        filters = TimelineFilters()
        result = timeline_manager.filter_snapshots(filters)
        
        assert len(result) == 3
        assert result == sample_snapshots
        timeline_manager.db_manager.list_snapshots.assert_called_once()
    
    def test_filter_snapshots_by_action_type(self, timeline_manager, sample_snapshots):
        """Test filtering snapshots by action type."""
        timeline_manager.db_manager.list_snapshots.return_value = sample_snapshots
        
        filters = TimelineFilters(action_types=["edit_file"])
        result = timeline_manager.filter_snapshots(filters)
        
        assert len(result) == 1
        assert result[0].action_type == "edit_file"
    
    def test_filter_snapshots_by_date_range(self, timeline_manager, sample_snapshots):
        """Test filtering snapshots by date range."""
        timeline_manager.db_manager.list_snapshots.return_value = sample_snapshots
        
        now = datetime.now()
        start_date = now - timedelta(hours=1, minutes=30)
        end_date = now + timedelta(minutes=30)
        
        filters = TimelineFilters(date_range=(start_date, end_date))
        result = timeline_manager.filter_snapshots(filters)
        
        assert len(result) == 2  # Should include last 2 snapshots
        assert all(start_date <= s.timestamp <= end_date for s in result)
    
    def test_filter_snapshots_by_file_patterns(self, timeline_manager, sample_snapshots):
        """Test filtering snapshots by file patterns."""
        timeline_manager.db_manager.list_snapshots.return_value = sample_snapshots
        
        filters = TimelineFilters(file_patterns=["*.py"])
        result = timeline_manager.filter_snapshots(filters)
        
        assert len(result) == 3  # All snapshots affect .py files
        
        # Test more specific pattern
        filters = TimelineFilters(file_patterns=["tests/*"])
        result = timeline_manager.filter_snapshots(filters)
        
        assert len(result) == 1  # Only one snapshot affects test files
        assert any("tests/" in str(f) for f in result[0].files_affected)
    
    def test_filter_snapshots_bookmarked_only(self, timeline_manager, sample_snapshots):
        """Test filtering snapshots to show only bookmarked ones."""
        timeline_manager.db_manager.list_snapshots.return_value = sample_snapshots
        
        # Add bookmark to first snapshot
        timeline_manager._bookmarks[sample_snapshots[0].id] = "Important change"
        
        filters = TimelineFilters(bookmarked_only=True)
        result = timeline_manager.filter_snapshots(filters)
        
        assert len(result) == 1
        assert result[0].id == sample_snapshots[0].id
    
    def test_search_snapshots(self, timeline_manager, sample_snapshots):
        """Test searching snapshots by query."""
        timeline_manager.db_manager.list_snapshots.return_value = sample_snapshots
        
        # Search by action type
        result = timeline_manager.search_snapshots("edit")
        assert len(result) == 1
        assert result[0].action_type == "edit_file"
        
        # Search by prompt context
        result = timeline_manager.search_snapshots("type hints")
        assert len(result) == 1
        assert "type hints" in result[0].prompt_context.lower()
        
        # Search by ID (partial)
        snapshot_id_part = sample_snapshots[0].id[:5]
        result = timeline_manager.search_snapshots(snapshot_id_part)
        assert len(result) == 1
        assert result[0].id == sample_snapshots[0].id
        
        # Case insensitive search
        result = timeline_manager.search_snapshots("API")
        assert len(result) >= 1  # Should find snapshots with "api" in context
    
    def test_bookmark_snapshot_success(self, timeline_manager, sample_snapshots):
        """Test successfully adding a bookmark to a snapshot."""
        snapshot = sample_snapshots[0]
        timeline_manager.db_manager.get_snapshot.return_value = snapshot
        
        result = timeline_manager.bookmark_snapshot(snapshot.id, "Important fix")
        
        assert result is True
        assert timeline_manager._bookmarks[snapshot.id] == "Important fix"
        timeline_manager.db_manager.get_snapshot.assert_called_once_with(snapshot.id)
    
    def test_bookmark_snapshot_not_found(self, timeline_manager):
        """Test bookmarking a non-existent snapshot."""
        timeline_manager.db_manager.get_snapshot.return_value = None
        
        result = timeline_manager.bookmark_snapshot("nonexistent", "Test bookmark")
        
        assert result is False
        assert "nonexistent" not in timeline_manager._bookmarks
    
    def test_bookmark_snapshot_database_error(self, timeline_manager):
        """Test bookmarking when database error occurs."""
        timeline_manager.db_manager.get_snapshot.side_effect = Exception("Database error")
        
        result = timeline_manager.bookmark_snapshot("test_id", "Test bookmark")
        
        assert result is False
        assert "test_id" not in timeline_manager._bookmarks
    
    def test_format_size(self, timeline_manager):
        """Test file size formatting."""
        assert timeline_manager._format_size(512) == "512B"
        assert timeline_manager._format_size(1024) == "1.0KB"
        assert timeline_manager._format_size(1536) == "1.5KB"
        assert timeline_manager._format_size(1024 * 1024) == "1.0MB"
        assert timeline_manager._format_size(1024 * 1024 * 1024) == "1.0GB"
    
    def test_apply_filters_and_search_combined(self, timeline_manager, sample_snapshots):
        """Test applying both filters and search together."""
        timeline_manager.db_manager.list_snapshots.return_value = sample_snapshots
        
        # Filter by action type and search by context
        filters = TimelineFilters(action_types=["edit_file", "create_file"])
        result = timeline_manager._apply_filters_and_search(sample_snapshots, filters, "API")
        
        # Should find snapshots that match both action type filter and search query
        assert len(result) >= 1
        assert all(s.action_type in ["edit_file", "create_file"] for s in result)
        assert all("api" in s.prompt_context.lower() for s in result)
    
    def test_show_interactive_timeline_no_snapshots(self, timeline_manager):
        """Test interactive timeline when no snapshots exist."""
        timeline_manager.db_manager.list_snapshots.return_value = []
        
        timeline_manager.show_interactive_timeline()
        
        # Should print message about no snapshots
        timeline_manager.console.print.assert_called()
        print_calls = [call.args[0] for call in timeline_manager.console.print.call_args_list]
        assert any("No snapshots found" in str(call) for call in print_calls)
    
    @patch('claude_rewind.core.timeline.Prompt')
    def test_show_interactive_timeline_quit_immediately(self, mock_prompt, timeline_manager, sample_snapshots):
        """Test interactive timeline when user quits immediately."""
        timeline_manager.db_manager.list_snapshots.return_value = sample_snapshots
        mock_prompt.ask.return_value = "q"
        
        timeline_manager.show_interactive_timeline()
        
        # Should call prompt and exit
        mock_prompt.ask.assert_called()
        timeline_manager.console.clear.assert_called()
    
    def test_database_error_handling(self, timeline_manager):
        """Test handling of database errors."""
        timeline_manager.db_manager.list_snapshots.side_effect = Exception("Database connection failed")
        
        # filter_snapshots should return empty list on error
        result = timeline_manager.filter_snapshots(TimelineFilters())
        assert result == []
        
        # search_snapshots should return empty list on error
        result = timeline_manager.search_snapshots("test")
        assert result == []
    
    def test_multiple_action_types_filter(self, timeline_manager, sample_snapshots):
        """Test filtering with multiple action types."""
        timeline_manager.db_manager.list_snapshots.return_value = sample_snapshots
        
        filters = TimelineFilters(action_types=["edit_file", "refactor"])
        result = timeline_manager.filter_snapshots(filters)
        
        assert len(result) == 2
        assert all(s.action_type in ["edit_file", "refactor"] for s in result)
    
    def test_multiple_file_patterns_filter(self, timeline_manager, sample_snapshots):
        """Test filtering with multiple file patterns."""
        timeline_manager.db_manager.list_snapshots.return_value = sample_snapshots
        
        filters = TimelineFilters(file_patterns=["src/*", "tests/*"])
        result = timeline_manager.filter_snapshots(filters)
        
        assert len(result) == 3  # All snapshots should match these patterns
    
    def test_empty_search_query(self, timeline_manager, sample_snapshots):
        """Test search with empty query returns all snapshots."""
        timeline_manager.db_manager.list_snapshots.return_value = sample_snapshots
        
        result = timeline_manager.search_snapshots("")
        
        assert len(result) == 3
        assert result == sample_snapshots
    
    def test_case_insensitive_search(self, timeline_manager, sample_snapshots):
        """Test that search is case insensitive."""
        timeline_manager.db_manager.list_snapshots.return_value = sample_snapshots
        
        # Test different cases
        result_lower = timeline_manager.search_snapshots("api")
        result_upper = timeline_manager.search_snapshots("API")
        result_mixed = timeline_manager.search_snapshots("Api")
        
        assert result_lower == result_upper == result_mixed
        assert len(result_lower) >= 1


class TestTimelineFilters:
    """Test cases for TimelineFilters functionality."""
    
    def test_timeline_filters_default(self):
        """Test default TimelineFilters values."""
        filters = TimelineFilters()
        
        assert filters.date_range is None
        assert filters.action_types is None
        assert filters.file_patterns is None
        assert filters.bookmarked_only is False
    
    def test_timeline_filters_with_values(self):
        """Test TimelineFilters with custom values."""
        start_date = datetime.now() - timedelta(days=1)
        end_date = datetime.now()
        
        filters = TimelineFilters(
            date_range=(start_date, end_date),
            action_types=["edit_file", "create_file"],
            file_patterns=["*.py", "*.js"],
            bookmarked_only=True
        )
        
        assert filters.date_range == (start_date, end_date)
        assert filters.action_types == ["edit_file", "create_file"]
        assert filters.file_patterns == ["*.py", "*.js"]
        assert filters.bookmarked_only is True


class TestTimelineIntegration:
    """Integration tests for timeline functionality."""
    
    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Create temporary database path."""
        return tmp_path / "test_timeline.db"
    
    @pytest.fixture
    def real_db_manager(self, temp_db_path):
        """Create real DatabaseManager for integration tests."""
        return DatabaseManager(temp_db_path)
    
    @pytest.fixture
    def timeline_manager_real(self, real_db_manager):
        """Create TimelineManager with real database."""
        return TimelineManager(real_db_manager)
    
    def test_timeline_with_real_database(self, timeline_manager_real, real_db_manager):
        """Test timeline functionality with real database."""
        # Create test snapshots
        now = datetime.now()
        
        snapshot1 = SnapshotMetadata(
            id=generate_snapshot_id(),
            timestamp=now - timedelta(hours=1),
            action_type="edit_file",
            prompt_context="Test snapshot 1",
            files_affected=[Path("test1.py")],
            total_size=100,
            compression_ratio=0.8
        )
        
        snapshot2 = SnapshotMetadata(
            id=generate_snapshot_id(),
            timestamp=now,
            action_type="create_file",
            prompt_context="Test snapshot 2",
            files_affected=[Path("test2.py")],
            total_size=200,
            compression_ratio=0.7
        )
        
        # Store snapshots in database
        real_db_manager.create_snapshot(snapshot1)
        real_db_manager.create_snapshot(snapshot2)
        
        # Test filtering
        filters = TimelineFilters(action_types=["edit_file"])
        result = timeline_manager_real.filter_snapshots(filters)
        
        assert len(result) == 1
        assert result[0].action_type == "edit_file"
        
        # Test search
        result = timeline_manager_real.search_snapshots("Test snapshot 1")
        
        assert len(result) == 1
        assert result[0].prompt_context == "Test snapshot 1"
        
        # Test bookmarking
        success = timeline_manager_real.bookmark_snapshot(snapshot1.id, "Important test")
        
        assert success is True
        assert timeline_manager_real._bookmarks[snapshot1.id] == "Important test"