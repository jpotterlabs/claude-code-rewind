"""Unit tests for database operations."""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

from claude_rewind.storage.database import DatabaseManager, DatabaseError
from claude_rewind.storage.migrations import MigrationManager, MigrationError
from claude_rewind.core.models import SnapshotMetadata, FileChange, ChangeType


class TestDatabaseManager:
    """Test cases for DatabaseManager."""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir) / "test.db"
    
    @pytest.fixture
    def db_manager(self, temp_db_path):
        """Create database manager instance."""
        return DatabaseManager(temp_db_path)
    
    @pytest.fixture
    def sample_metadata(self):
        """Create sample snapshot metadata."""
        return SnapshotMetadata(
            id="test_snapshot_001",
            timestamp=datetime.now(),
            action_type="edit_file",
            prompt_context="Add type hints to API",
            files_affected=[Path("src/api.py"), Path("tests/test_api.py")],
            total_size=1024,
            compression_ratio=0.7,
            parent_snapshot=None
        )
    
    def test_database_initialization(self, temp_db_path):
        """Test database and table creation."""
        db_manager = DatabaseManager(temp_db_path)
        
        # Check database file exists
        assert temp_db_path.exists()
        
        # Check tables exist
        with sqlite3.connect(str(temp_db_path)) as conn:
            cursor = conn.cursor()
            
            # Check snapshots table
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='snapshots'
            """)
            assert cursor.fetchone() is not None
            
            # Check file_changes table
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='file_changes'
            """)
            assert cursor.fetchone() is not None
            
            # Check schema_info table
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='schema_info'
            """)
            assert cursor.fetchone() is not None
    
    def test_schema_version(self, db_manager):
        """Test schema version management."""
        version = db_manager.get_schema_version()
        assert version == db_manager.SCHEMA_VERSION
    
    def test_create_snapshot(self, db_manager, sample_metadata):
        """Test snapshot creation."""
        db_manager.create_snapshot(sample_metadata)
        
        # Verify snapshot was created
        retrieved = db_manager.get_snapshot(sample_metadata.id)
        assert retrieved is not None
        assert retrieved.id == sample_metadata.id
        assert retrieved.action_type == sample_metadata.action_type
        assert retrieved.prompt_context == sample_metadata.prompt_context
        assert retrieved.total_size == sample_metadata.total_size
        assert retrieved.compression_ratio == sample_metadata.compression_ratio
    
    def test_get_nonexistent_snapshot(self, db_manager):
        """Test retrieving non-existent snapshot."""
        result = db_manager.get_snapshot("nonexistent")
        assert result is None
    
    def test_list_snapshots(self, db_manager):
        """Test listing snapshots."""
        # Create multiple snapshots
        snapshots = []
        for i in range(3):
            metadata = SnapshotMetadata(
                id=f"snapshot_{i:03d}",
                timestamp=datetime.now(),
                action_type="test_action",
                prompt_context=f"Test prompt {i}",
                files_affected=[],
                total_size=100 * i,
                compression_ratio=0.8,
                parent_snapshot=None
            )
            snapshots.append(metadata)
            db_manager.create_snapshot(metadata)
        
        # Test listing all
        all_snapshots = db_manager.list_snapshots()
        assert len(all_snapshots) == 3
        
        # Test with limit
        limited = db_manager.list_snapshots(limit=2)
        assert len(limited) == 2
        
        # Test with offset
        offset_snapshots = db_manager.list_snapshots(limit=2, offset=1)
        assert len(offset_snapshots) == 2
    
    def test_delete_snapshot(self, db_manager, sample_metadata):
        """Test snapshot deletion."""
        # Create snapshot
        db_manager.create_snapshot(sample_metadata)
        assert db_manager.get_snapshot(sample_metadata.id) is not None
        
        # Delete snapshot
        deleted = db_manager.delete_snapshot(sample_metadata.id)
        assert deleted is True
        
        # Verify deletion
        assert db_manager.get_snapshot(sample_metadata.id) is None
        
        # Test deleting non-existent snapshot
        deleted_again = db_manager.delete_snapshot(sample_metadata.id)
        assert deleted_again is False
    
    def test_file_changes(self, db_manager, sample_metadata):
        """Test file change operations."""
        # Create snapshot first
        db_manager.create_snapshot(sample_metadata)
        
        # Create file changes
        file_changes = [
            FileChange(
                path=Path("src/api.py"),
                change_type=ChangeType.MODIFIED,
                before_hash="hash1",
                after_hash="hash2",
                line_changes=[]
            ),
            FileChange(
                path=Path("tests/test_api.py"),
                change_type=ChangeType.ADDED,
                before_hash=None,
                after_hash="hash3",
                line_changes=[]
            )
        ]
        
        # Add file changes
        for change in file_changes:
            db_manager.add_file_change(sample_metadata.id, change)
        
        # Retrieve file changes
        retrieved_changes = db_manager.get_file_changes(sample_metadata.id)
        assert len(retrieved_changes) == 2
        
        # Verify change details
        api_change = next(c for c in retrieved_changes if c.path.name == "api.py")
        assert api_change.change_type == ChangeType.MODIFIED
        assert api_change.before_hash == "hash1"
        assert api_change.after_hash == "hash2"
        
        test_change = next(c for c in retrieved_changes if c.path.name == "test_api.py")
        assert test_change.change_type == ChangeType.ADDED
        assert test_change.before_hash is None
        assert test_change.after_hash == "hash3"
    
    def test_cleanup_old_snapshots(self, db_manager):
        """Test cleanup of old snapshots."""
        # Create 5 snapshots
        for i in range(5):
            metadata = SnapshotMetadata(
                id=f"snapshot_{i:03d}",
                timestamp=datetime.now(),
                action_type="test_action",
                prompt_context=f"Test prompt {i}",
                files_affected=[],
                total_size=100,
                compression_ratio=0.8,
                parent_snapshot=None
            )
            db_manager.create_snapshot(metadata)
        
        # Keep only 3 most recent
        deleted_count = db_manager.cleanup_old_snapshots(keep_count=3)
        assert deleted_count == 2
        
        # Verify only 3 remain
        remaining = db_manager.list_snapshots()
        assert len(remaining) == 3
    
    def test_storage_stats(self, db_manager, sample_metadata):
        """Test storage statistics."""
        # Initially empty
        stats = db_manager.get_storage_stats()
        assert stats['snapshot_count'] == 0
        assert stats['file_change_count'] == 0
        assert stats['total_content_size'] == 0
        
        # Add snapshot and file change
        db_manager.create_snapshot(sample_metadata)
        file_change = FileChange(
            path=Path("test.py"),
            change_type=ChangeType.ADDED,
            before_hash=None,
            after_hash="hash1",
            line_changes=[]
        )
        db_manager.add_file_change(sample_metadata.id, file_change)
        
        # Check updated stats
        stats = db_manager.get_storage_stats()
        assert stats['snapshot_count'] == 1
        assert stats['file_change_count'] == 1
        assert stats['total_content_size'] == sample_metadata.total_size
        assert stats['database_size'] > 0
    
    def test_database_error_handling(self, temp_db_path):
        """Test database error handling."""
        # Create database manager
        db_manager = DatabaseManager(temp_db_path)
        
        # Corrupt the database by writing invalid data
        with open(temp_db_path, 'w') as f:
            f.write("invalid sqlite data")
        
        # Operations should raise DatabaseError
        with pytest.raises(DatabaseError):
            db_manager.get_snapshot("test")
    
    def test_cascade_delete(self, db_manager, sample_metadata):
        """Test that file changes are deleted when snapshot is deleted."""
        # Create snapshot and file change
        db_manager.create_snapshot(sample_metadata)
        file_change = FileChange(
            path=Path("test.py"),
            change_type=ChangeType.ADDED,
            before_hash=None,
            after_hash="hash1",
            line_changes=[]
        )
        db_manager.add_file_change(sample_metadata.id, file_change)
        
        # Verify file change exists
        changes = db_manager.get_file_changes(sample_metadata.id)
        assert len(changes) == 1
        
        # Delete snapshot
        db_manager.delete_snapshot(sample_metadata.id)
        
        # Verify file changes are also deleted
        changes = db_manager.get_file_changes(sample_metadata.id)
        assert len(changes) == 0


class TestMigrationManager:
    """Test cases for MigrationManager."""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir) / "test.db"
    
    @pytest.fixture
    def db_manager(self, temp_db_path):
        """Create database manager instance."""
        return DatabaseManager(temp_db_path)
    
    @pytest.fixture
    def migration_manager(self, db_manager):
        """Create migration manager instance."""
        return MigrationManager(db_manager)
    
    def test_no_migration_needed(self, migration_manager):
        """Test when no migration is needed."""
        assert not migration_manager.needs_migration()
        assert migration_manager.get_pending_migrations() == []
    
    def test_migration_with_no_pending(self, migration_manager):
        """Test migration when no migrations are pending."""
        migration_manager.migrate()  # Should not raise any errors
    
    def test_backup_creation(self, migration_manager, temp_db_path):
        """Test database backup creation."""
        backup_path = temp_db_path.with_suffix('.backup')
        migration_manager.create_backup(backup_path)
        
        assert backup_path.exists()
        assert backup_path.stat().st_size > 0
    
    def test_migration_error_handling(self, migration_manager):
        """Test migration error handling."""
        # Mock a migration that fails
        def failing_migration(conn):
            raise Exception("Migration failed")
        
        migration_manager.migrations[999] = failing_migration
        
        # Mock needs_migration to return True
        with patch.object(migration_manager, 'needs_migration', return_value=True):
            with patch.object(migration_manager, 'get_pending_migrations', return_value=[999]):
                with pytest.raises(MigrationError):
                    migration_manager.migrate()
    
    def test_schema_version_update(self, migration_manager, db_manager):
        """Test that schema version is updated after migration."""
        initial_version = db_manager.get_schema_version()
        
        # Mock a successful migration
        def dummy_migration(conn):
            pass
        
        migration_manager.migrations[initial_version + 1] = dummy_migration
        
        with patch.object(migration_manager, 'needs_migration', return_value=True):
            with patch.object(migration_manager, 'get_pending_migrations', 
                            return_value=[initial_version + 1]):
                migration_manager.migrate()
        
        # Version should be updated
        new_version = db_manager.get_schema_version()
        assert new_version == initial_version + 1


if __name__ == "__main__":
    pytest.main([__file__])