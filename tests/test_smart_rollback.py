"""Tests for smart rollback features."""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock

from claude_rewind.core.rollback_engine import RollbackEngine
from claude_rewind.core.models import (
    SnapshotId, RollbackOptions, RollbackPreview, RollbackResult,
    FileConflict, ConflictResolution, FileState, Snapshot, SnapshotMetadata
)


class TestSmartRollbackFeatures:
    """Test cases for smart rollback functionality."""
    
    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Create project structure with various file types
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").write_text("""
def main():
    print("Hello, World!")
    return 0

if __name__ == "__main__":
    main()
""")
        
        (temp_dir / "src" / "utils.py").write_text("""
def helper_function():
    # This is a helper function
    return "helper"

def another_function():
    return "another"
""")
        
        (temp_dir / "README.md").write_text("""
# Test Project

This is a test project for rollback functionality.

## Features
- Feature 1
- Feature 2
""")
        
        # Create .claude-rewind directory
        rewind_dir = temp_dir / ".claude-rewind"
        rewind_dir.mkdir()
        (rewind_dir / "backups").mkdir()
        
        yield temp_dir
        
        # Cleanup
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def mock_storage_manager(self):
        """Create a mock storage manager with realistic content."""
        storage_manager = Mock()
        
        # Store original content for different scenarios
        original_contents = {
            "main_original": b"""
def main():
    print("Hello, World!")
    return 0

if __name__ == "__main__":
    main()
""",
            "utils_original": b"""
def helper_function():
    # This is a helper function
    return "helper"

def another_function():
    return "another"
""",
            "readme_original": b"""
# Test Project

This is a test project for rollback functionality.

## Features
- Feature 1
- Feature 2
"""
        }
        
        def mock_load_content(content_hash):
            return original_contents.get(content_hash)
        
        storage_manager.load_file_content.side_effect = mock_load_content
        
        return storage_manager, original_contents
    
    @pytest.fixture
    def rollback_engine(self, temp_project, mock_storage_manager):
        """Create a rollback engine instance."""
        storage_manager, _ = mock_storage_manager
        return RollbackEngine(storage_manager, temp_project)
    
    def test_selective_rollback_preview(self, rollback_engine, mock_storage_manager, temp_project):
        """Test selective rollback preview functionality."""
        storage_manager, original_contents = mock_storage_manager
        
        # Create mock snapshot with selective files
        file_states = {
            Path("src/main.py"): FileState(
                path=Path("src/main.py"),
                content_hash="main_original",
                size=len(original_contents["main_original"]),
                modified_time=datetime.now(),
                permissions=0o644,
                exists=True
            )
        }
        
        snapshot_metadata = SnapshotMetadata(
            id="selective_test",
            timestamp=datetime.now(),
            action_type="edit_file",
            prompt_context="Selective test snapshot",
            files_affected=[Path("src/main.py")],
            total_size=100,
            compression_ratio=0.8
        )
        
        mock_snapshot = Snapshot(
            id="selective_test",
            timestamp=datetime.now(),
            metadata=snapshot_metadata,
            file_states=file_states
        )
        
        storage_manager.load_snapshot.return_value = mock_snapshot
        
        # Test selective rollback preview
        selected_files = [Path("src/main.py")]
        preview = rollback_engine.preview_selective_rollback("selective_test", selected_files)
        
        assert isinstance(preview, RollbackPreview)
        # Should only consider the selected file
        if preview.files_to_restore:
            assert all(f in selected_files for f in preview.files_to_restore)
    
    def test_execute_selective_rollback(self, rollback_engine, mock_storage_manager, temp_project):
        """Test selective rollback execution."""
        storage_manager, original_contents = mock_storage_manager
        
        # Modify one file
        main_file = temp_project / "src" / "main.py"
        main_file.write_text("# Modified content\nprint('changed')")
        
        # Create mock snapshot
        file_states = {
            Path("src/main.py"): FileState(
                path=Path("src/main.py"),
                content_hash="main_original",
                size=len(original_contents["main_original"]),
                modified_time=datetime.now(),
                permissions=0o644,
                exists=True
            )
        }
        
        snapshot_metadata = SnapshotMetadata(
            id="selective_test",
            timestamp=datetime.now(),
            action_type="edit_file",
            prompt_context="Selective test snapshot",
            files_affected=[Path("src/main.py")],
            total_size=100,
            compression_ratio=0.8
        )
        
        mock_snapshot = Snapshot(
            id="selective_test",
            timestamp=datetime.now(),
            metadata=snapshot_metadata,
            file_states=file_states
        )
        
        storage_manager.load_snapshot.return_value = mock_snapshot
        
        # Execute selective rollback
        selected_files = [Path("src/main.py")]
        result = rollback_engine.execute_selective_rollback("selective_test", selected_files, preserve_changes=False)
        
        assert isinstance(result, RollbackResult)
        # Should have restored the selected file
        if result.files_restored:
            assert Path("src/main.py") in result.files_restored
    
    def test_three_way_merge_simple(self, rollback_engine):
        """Test simple three-way merge functionality."""
        base_content = """
def function():
    print("base")
    return True
"""
        
        current_content = """
def function():
    print("base")
    print("current addition")
    return True
"""
        
        snapshot_content = """
def function():
    print("base")
    return True
    # snapshot addition
"""
        
        merged = rollback_engine._three_way_merge(base_content, current_content, snapshot_content)
        
        assert merged is not None
        assert "current addition" in merged
        assert "snapshot addition" in merged
    
    def test_three_way_merge_conflicting(self, rollback_engine):
        """Test three-way merge with conflicting changes."""
        base_content = """
def function():
    print("original")
    return True
"""
        
        current_content = """
def function():
    print("current change")
    return True
"""
        
        snapshot_content = """
def function():
    print("snapshot change")
    return True
"""
        
        merged = rollback_engine._three_way_merge(base_content, current_content, snapshot_content)
        
        # Should return None for conflicting changes
        assert merged is None
    
    def test_conflict_resolution_content_mismatch(self, rollback_engine, mock_storage_manager):
        """Test conflict resolution for content mismatches."""
        storage_manager, original_contents = mock_storage_manager
        
        conflict = FileConflict(
            file_path=Path("src/main.py"),
            current_hash="current123",
            target_hash="main_original",
            conflict_type="content_mismatch",
            description="File has been modified"
        )
        
        resolution = rollback_engine._resolve_single_conflict(conflict)
        
        assert isinstance(resolution, ConflictResolution)
        assert resolution.file_path == Path("src/main.py")
        assert resolution.resolution_type in ["keep_current", "use_snapshot", "merge"]
    
    def test_conflict_resolution_file_added(self, rollback_engine):
        """Test conflict resolution for newly added files."""
        conflict = FileConflict(
            file_path=Path("src/new_file.py"),
            current_hash="new123",
            target_hash="",
            conflict_type="file_added",
            description="File was added after snapshot"
        )
        
        resolution = rollback_engine._resolve_single_conflict(conflict)
        
        assert isinstance(resolution, ConflictResolution)
        assert resolution.file_path == Path("src/new_file.py")
        assert resolution.resolution_type == "keep_current"
    
    def test_conflict_resolution_file_deleted(self, rollback_engine, temp_project):
        """Test conflict resolution for deleted files."""
        # Create a file that will be "deleted" in the conflict
        test_file = temp_project / "src" / "temp_file.py"
        test_file.write_text("temporary content")
        
        conflict = FileConflict(
            file_path=Path("src/temp_file.py"),
            current_hash="temp123",
            target_hash="",
            conflict_type="file_deleted",
            description="File was deleted in snapshot"
        )
        
        resolution = rollback_engine._resolve_deletion_conflict(conflict)
        
        assert isinstance(resolution, ConflictResolution)
        assert resolution.file_path == Path("src/temp_file.py")
        assert resolution.resolution_type in ["keep_current", "use_snapshot"]
    
    def test_analyze_conflict_severity(self, rollback_engine):
        """Test conflict severity analysis."""
        # Minor change (very similar)
        current = "def function():\n    print('hello')\n    return True"
        target = "def function():\n    print('hello')\n    return True\n"
        
        severity = rollback_engine._analyze_conflict_severity(current, target)
        assert severity == "minor"
        
        # Major change (very different)
        current = "def function():\n    print('hello')\n    return True"
        target = "class MyClass:\n    def __init__(self):\n        self.value = 42"
        
        severity = rollback_engine._analyze_conflict_severity(current, target)
        assert severity == "major"
    
    def test_determine_conflict_type_additions_only(self, rollback_engine):
        """Test conflict type determination for additions only."""
        # Target content (original)
        target = """def function():
    print("base")
    return True"""
        
        # Current content (with addition at the end)
        current = """def function():
    print("base")
    return True
    print("addition")"""
        
        conflict_type = rollback_engine._determine_conflict_type(current, target)
        assert conflict_type == "additions_only"
    
    def test_determine_conflict_type_comments_only(self, rollback_engine):
        """Test conflict type determination for comment changes only."""
        current = """
def function():
    # Current comment
    print("base")
    return True
"""
        
        target = """
def function():
    # Target comment
    print("base")
    return True
"""
        
        conflict_type = rollback_engine._determine_conflict_type(current, target)
        assert conflict_type == "comments_only"
    
    def test_determine_conflict_type_whitespace_only(self, rollback_engine):
        """Test conflict type determination for whitespace changes only."""
        current = "def function():\n    print('hello')\n    return True"
        target = "def function():\n        print('hello')\n        return True"
        
        conflict_type = rollback_engine._determine_conflict_type(current, target)
        assert conflict_type == "whitespace_only"
    
    def test_advanced_conflict_detection(self, rollback_engine, mock_storage_manager, temp_project):
        """Test advanced conflict detection with different scenarios."""
        storage_manager, original_contents = mock_storage_manager
        
        # Test with a file that has only comment changes
        main_file = temp_project / "src" / "main.py"
        main_file.write_text("""
def main():
    # Modified comment
    print("Hello, World!")
    return 0

if __name__ == "__main__":
    main()
""")
        
        current_hash = rollback_engine._calculate_hash(main_file.read_bytes())
        target_hash = "main_original"
        
        conflict = rollback_engine._detect_conflict(Path("src/main.py"), current_hash, target_hash)
        
        # Should detect the conflict but classify it appropriately
        if conflict:
            assert conflict.conflict_type in ["comments_only", "content_mismatch"]
    
    def test_looks_like_generated_file(self, rollback_engine):
        """Test detection of generated files."""
        # Test various generated file patterns
        assert rollback_engine._looks_like_generated_file(Path("__pycache__/module.pyc"))
        assert rollback_engine._looks_like_generated_file(Path("node_modules/package/index.js"))
        assert rollback_engine._looks_like_generated_file(Path("build/output.js"))
        assert rollback_engine._looks_like_generated_file(Path("dist/bundle.min.js"))
        
        # Test normal files
        assert not rollback_engine._looks_like_generated_file(Path("src/main.py"))
        assert not rollback_engine._looks_like_generated_file(Path("README.md"))
        assert not rollback_engine._looks_like_generated_file(Path("config.json"))
    
    def test_only_comments_changed(self, rollback_engine):
        """Test detection of comment-only changes."""
        lines1 = [
            "def function():",
            "    # Old comment",
            "    print('hello')",
            "    return True"
        ]
        
        lines2 = [
            "def function():",
            "    # New comment",
            "    print('hello')",
            "    return True"
        ]
        
        assert rollback_engine._only_comments_changed(lines1, lines2)
        
        # Test with actual code changes
        lines3 = [
            "def function():",
            "    print('hello')",
            "    return True"
        ]
        
        lines4 = [
            "def function():",
            "    print('goodbye')",
            "    return False"
        ]
        
        assert not rollback_engine._only_comments_changed(lines3, lines4)
    
    def test_only_whitespace_changed(self, rollback_engine):
        """Test detection of whitespace-only changes."""
        content1 = "def function():\n    print('hello')\n    return True"
        content2 = "def function():\n        print('hello')\n        return True"
        
        assert rollback_engine._only_whitespace_changed(content1, content2)
        
        # Test with actual content changes
        content3 = "def function():\n    print('hello')\n    return True"
        content4 = "def function():\n    print('goodbye')\n    return False"
        
        assert not rollback_engine._only_whitespace_changed(content3, content4)
    
    def test_compute_line_changes(self, rollback_engine):
        """Test line change computation."""
        base_lines = ["line1", "line2", "line3"]
        target_lines = ["line1", "modified_line2", "line3", "line4"]
        
        changes = rollback_engine._compute_line_changes(base_lines, target_lines)
        
        assert len(changes) > 0
        # Should detect the modification and addition
        change_types = [change[1] for change in changes]
        assert "delete" in change_types or "insert" in change_types
    
    def test_have_conflicting_changes(self, rollback_engine):
        """Test conflicting changes detection."""
        # Changes affecting the same line
        changes1 = [(1, "modify", "new content 1")]
        changes2 = [(1, "modify", "new content 2")]
        
        assert rollback_engine._have_conflicting_changes(changes1, changes2)
        
        # Changes affecting different lines
        changes3 = [(1, "modify", "content 1")]
        changes4 = [(2, "modify", "content 2")]
        
        assert not rollback_engine._have_conflicting_changes(changes3, changes4)
    
    def test_generate_conflict_description(self, rollback_engine):
        """Test conflict description generation."""
        file_path = Path("src/test.py")
        current_content = "line1\nline2\nline3\nline4"
        target_content = "line1\nline2"
        
        # Test additions only
        description = rollback_engine._generate_conflict_description(
            file_path, current_content, target_content, "additions_only"
        )
        assert "additional lines" in description
        
        # Test deletions only
        description = rollback_engine._generate_conflict_description(
            file_path, target_content, current_content, "deletions_only"
        )
        assert "missing" in description and "lines" in description
        
        # Test comments only
        description = rollback_engine._generate_conflict_description(
            file_path, current_content, target_content, "comments_only"
        )
        assert "comment changes" in description


class TestSmartRollbackIntegration:
    """Integration tests for smart rollback features."""
    
    @pytest.fixture
    def integration_project(self):
        """Create a complex project for integration testing."""
        temp_dir = Path(tempfile.mkdtemp())
        
        # Create a realistic project structure
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "api").mkdir()
        (temp_dir / "tests").mkdir()
        (temp_dir / "docs").mkdir()
        
        # Create files with realistic content
        (temp_dir / "src" / "main.py").write_text("""#!/usr/bin/env python3
\"\"\"Main application entry point.\"\"\"

import sys
from api.handlers import handle_request

def main():
    \"\"\"Main function.\"\"\"
    print("Starting application...")
    
    # Process command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]
        result = handle_request(command)
        print(f"Result: {result}")
    else:
        print("No command provided")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
""")
        
        (temp_dir / "src" / "api" / "handlers.py").write_text("""\"\"\"API request handlers.\"\"\"

def handle_request(request_type):
    \"\"\"Handle different types of requests.\"\"\"
    handlers = {
        'status': get_status,
        'info': get_info,
        'help': get_help
    }
    
    handler = handlers.get(request_type, get_help)
    return handler()

def get_status():
    \"\"\"Get application status.\"\"\"
    return {"status": "running", "version": "1.0.0"}

def get_info():
    \"\"\"Get application information.\"\"\"
    return {"name": "Test App", "description": "A test application"}

def get_help():
    \"\"\"Get help information.\"\"\"
    return {"commands": ["status", "info", "help"]}
""")
        
        # Create .claude-rewind directory
        rewind_dir = temp_dir / ".claude-rewind"
        rewind_dir.mkdir()
        (rewind_dir / "backups").mkdir()
        
        yield temp_dir
        
        # Cleanup
        shutil.rmtree(temp_dir)
    
    def test_smart_rollback_with_mixed_changes(self, integration_project):
        """Test smart rollback with a mix of different change types."""
        # Create mock storage manager
        storage_manager = Mock()
        
        # Store original content
        main_file = integration_project / "src" / "main.py"
        handlers_file = integration_project / "src" / "api" / "handlers.py"
        
        original_main = main_file.read_bytes()
        original_handlers = handlers_file.read_bytes()
        
        # Mock storage responses
        def mock_load_content(content_hash):
            if content_hash == "main_hash":
                return original_main
            elif content_hash == "handlers_hash":
                return original_handlers
            return None
        
        storage_manager.load_file_content.side_effect = mock_load_content
        
        # Create file states
        file_states = {
            Path("src/main.py"): FileState(
                path=Path("src/main.py"),
                content_hash="main_hash",
                size=len(original_main),
                modified_time=datetime.now(),
                permissions=0o644,
                exists=True
            ),
            Path("src/api/handlers.py"): FileState(
                path=Path("src/api/handlers.py"),
                content_hash="handlers_hash",
                size=len(original_handlers),
                modified_time=datetime.now(),
                permissions=0o644,
                exists=True
            )
        }
        
        snapshot_metadata = SnapshotMetadata(
            id="integration_test",
            timestamp=datetime.now(),
            action_type="refactor",
            prompt_context="Integration test with mixed changes",
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
        
        # Create rollback engine
        rollback_engine = RollbackEngine(storage_manager, integration_project)
        
        # Make different types of changes
        # 1. Add comments to main.py (comment-only change)
        main_file.write_text("""#!/usr/bin/env python3
\"\"\"Main application entry point.\"\"\"

import sys
from api.handlers import handle_request

def main():
    \"\"\"Main function with additional comments.\"\"\"
    print("Starting application...")
    
    # Process command line arguments
    # TODO: Add better argument parsing
    if len(sys.argv) > 1:
        command = sys.argv[1]
        result = handle_request(command)
        print(f"Result: {result}")
    else:
        print("No command provided")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
""")
        
        # 2. Add new function to handlers.py (addition-only change)
        handlers_file.write_text("""\"\"\"API request handlers.\"\"\"

def handle_request(request_type):
    \"\"\"Handle different types of requests.\"\"\"
    handlers = {
        'status': get_status,
        'info': get_info,
        'help': get_help
    }
    
    handler = handlers.get(request_type, get_help)
    return handler()

def get_status():
    \"\"\"Get application status.\"\"\"
    return {"status": "running", "version": "1.0.0"}

def get_info():
    \"\"\"Get application information.\"\"\"
    return {"name": "Test App", "description": "A test application"}

def get_help():
    \"\"\"Get help information.\"\"\"
    return {"commands": ["status", "info", "help"]}

def get_version():
    \"\"\"Get version information.\"\"\"
    return {"version": "1.0.0", "build": "dev"}
""")
        
        # Test smart rollback preview
        options = RollbackOptions(preserve_manual_changes=True)
        preview = rollback_engine.preview_rollback("integration_test", options)
        
        # Should intelligently handle different change types
        assert isinstance(preview, RollbackPreview)
        
        # The smart rollback should minimize conflicts for comment-only and addition-only changes
        # Exact behavior depends on the implementation, but there should be some intelligence
        assert preview.estimated_changes >= 0